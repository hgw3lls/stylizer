import json
import zipfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from app import config
from app.db import Base, get_engine, reset_engine
from app.main import create_app, get_analyzer, get_fusion_planner, get_translator
from app.schemas import Constraints, FusionPlan, PromptAnchors, StylePack, TranslateOptions, VariabilityKnobs


class MockAnalyzer:
    def analyze(self, image_paths: list[str], validation_errors: str | None = None) -> tuple[Constraints, PromptAnchors]:
        return (
            Constraints(
                palette=["#111111", "#eeeeee"],
                materials=["paper"],
                line_rules=["thin lines"],
                composition_rules=["strong framing"],
                translation_rules=["preserve contrast"],
                forbidden=["text"],
            ),
            PromptAnchors(
                base_prompt="retain monochrome elegance",
                negative_prompt="avoid logos",
                variability_knobs=VariabilityKnobs(drift=0.1, density=0.7, abstraction=0.2),
            ),
        )


class MockTranslator:
    def translate_single(
        self,
        prompt: str,
        source_image: bytes,
        source_mime_type: str,
        options: TranslateOptions,
    ) -> list[str]:
        assert source_mime_type == "image/png"
        return ["ZmFrZS1pbWFnZS1iYXNlNjQ="]


class MockFusionPlanner:
    def generate_plan(self, image_inputs: list[tuple[bytes, str]], options: TranslateOptions) -> FusionPlan:
        assert len(image_inputs) >= 2
        assert options.fusion_strategy in {"collage", "poseA_bgB", "motif_fusion"}
        return FusionPlan(
            subject_from=0,
            background_from=1,
            motifs_from=[0, 1],
            composition_notes="subject from 0, bg from 1",
            exclusions=["logos"],
            dominance_weights=[0.6, 0.4],
        )


def make_client(
    tmp_path: Path,
    with_mock_analyzer: bool = False,
    with_mock_translator: bool = False,
    with_mock_fusion_planner: bool = False,
) -> TestClient:
    config.settings.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    config.settings.assets_root = str(tmp_path / "assets")
    reset_engine()
    Base.metadata.create_all(get_engine())
    app = create_app()
    if with_mock_analyzer:
        app.dependency_overrides[get_analyzer] = lambda: MockAnalyzer()
    if with_mock_translator:
        app.dependency_overrides[get_translator] = lambda: MockTranslator()
    if with_mock_fusion_planner:
        app.dependency_overrides[get_fusion_planner] = lambda: MockFusionPlanner()
    return TestClient(app)


def create_pack(client: TestClient) -> StylePack:
    response = client.post(
        "/style-packs",
        data={"name": "Neo Deco"},
        files=[("images", ("style.png", BytesIO(b"img"), "image/png"))],
    )
    assert response.status_code == 200
    return StylePack.model_validate(response.json())


def test_health(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_fetch_style_pack(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    body = create_pack(client)

    assert body.name == "Neo Deco"
    assert len(body.style_images) == 1
    assert body.style_images[0].mime_type == "image/png"
    assert Path(body.style_images[0].path).exists()

    list_response = client.get("/style-packs")
    assert list_response.status_code == 200
    packs = [StylePack.model_validate(item) for item in list_response.json()]
    assert len(packs) == 1

    detail_response = client.get(f"/style-packs/{body.id}")
    assert detail_response.status_code == 200
    detail = StylePack.model_validate(detail_response.json())
    assert detail.id == body.id


def test_analyze_style_pack_saves_constraints(tmp_path: Path) -> None:
    client = make_client(tmp_path, with_mock_analyzer=True)
    style_pack = create_pack(client)

    analyze_response = client.post(f"/style-packs/{style_pack.id}/analyze")
    assert analyze_response.status_code == 200

    analyzed = StylePack.model_validate(analyze_response.json())
    assert analyzed.constraints.palette == ["#111111", "#eeeeee"]
    assert analyzed.prompt_anchors.base_prompt == "retain monochrome elegance"


def test_translate_with_mocked_openai_call(tmp_path: Path) -> None:
    client = make_client(tmp_path, with_mock_translator=True)
    style_pack = create_pack(client)

    response = client.post(
        "/translate",
        data={
            "style_pack_id": style_pack.id,
            "mode": "translate_single",
            "options": '{"size":"1024x1024","quality":"high","variations":1,"preserve_composition":true}',
        },
        files=[("input_images", ("input.png", BytesIO(b"source"), "image/png"))],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["style_pack_id"] == style_pack.id
    assert body["mode"] == "translate_single"
    assert len(body["images"]) == 1


def test_synthesize_multi_with_mocked_fusion_planner(tmp_path: Path) -> None:
    client = make_client(tmp_path, with_mock_translator=True, with_mock_fusion_planner=True)
    style_pack = create_pack(client)

    response = client.post(
        "/translate",
        data={
            "style_pack_id": style_pack.id,
            "mode": "synthesize_multi",
            "options": '{"size":"1024x1024","quality":"high","fusion_strategy":"collage","variations":2}',
        },
        files=[
            ("input_images", ("a.png", BytesIO(b"source-a"), "image/png")),
            ("input_images", ("b.png", BytesIO(b"source-b"), "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "synthesize_multi"
    assert len(body["images"]) >= 2
    assert body["images"][0]["fusion_plan"]["subject_from"] == 0



def test_history_lists_recent_jobs(tmp_path: Path) -> None:
    client = make_client(tmp_path, with_mock_translator=True)
    style_pack = create_pack(client)

    translate_response = client.post(
        "/translate",
        data={
            "style_pack_id": style_pack.id,
            "mode": "translate_single",
            "options": '{"size":"1024x1024","quality":"high","variations":1,"preserve_composition":true}',
        },
        files=[("input_images", ("input.png", BytesIO(b"source"), "image/png"))],
    )
    assert translate_response.status_code == 200

    jobs_response = client.get("/jobs")
    assert jobs_response.status_code == 200
    body = jobs_response.json()
    assert len(body) >= 1
    assert body[0]["style_pack_id"] == style_pack.id


def test_translate_job_lifecycle(tmp_path: Path) -> None:
    client = make_client(tmp_path, with_mock_translator=True)
    style_pack = create_pack(client)

    create_job = client.post(
        "/jobs/translate",
        data={
            "style_pack_id": style_pack.id,
            "mode": "translate_single",
            "options": '{"size":"1024x1024","quality":"high","variations":1,"preserve_composition":true}',
        },
        files=[("input_images", ("input.png", BytesIO(b"source"), "image/png"))],
    )
    assert create_job.status_code == 200
    job_id = create_job.json()["job_id"]

    status = client.get(f"/jobs/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] in {"running", "completed"}
    if body["status"] == "completed":
        assert body["result"]["mode"] == "translate_single"

def test_style_pack_not_found(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/style-packs/missing")

    assert response.status_code == 404


def test_export_style_pack_archive_contains_manifest_and_images(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    style_pack = create_pack(client)

    response = client.get(f"/style-packs/{style_pack.id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "style_pack.json" in names
        manifest = json.loads(archive.read("style_pack.json"))
        assert manifest["name"] == "Neo Deco"
        assert len(manifest["style_images"]) == 1
        image_path = manifest["style_images"][0]["path"]
        assert image_path in names
        assert archive.read(image_path) == b"img"


def test_import_style_pack_archive_recreates_pack(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    style_pack = create_pack(client)
    export_response = client.get(f"/style-packs/{style_pack.id}/export")
    assert export_response.status_code == 200

    import_response = client.post(
        "/style-packs/import",
        files=[("archive", ("pack.zip", BytesIO(export_response.content), "application/zip"))],
    )

    assert import_response.status_code == 200
    imported = StylePack.model_validate(import_response.json())
    assert imported.id != style_pack.id
    assert imported.name == style_pack.name
    assert imported.constraints.forbidden == style_pack.constraints.forbidden
    assert len(imported.style_images) == 1
    assert Path(imported.style_images[0].path).exists()

