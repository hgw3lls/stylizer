import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.analyzer import StylePackAnalyzer, analyze_with_retry, build_default_analyzer
from app.config import settings
from app.db import Base, get_engine, get_session
from app.models import AssetModel, StylePackModel, TranslationJobModel, TranslationOutputModel
from app.schemas import (
    Constraints,
    CreateJobResponse,
    FusionPlan,
    HealthResponse,
    JobOutput,
    JobStatusResponse,
    PromptAnchors,
    StyleImageRef,
    StylePack,
    TranslateOptions,
    TranslateResponse,
    TranslationImage,
    TranslationJob,
    VariabilityKnobs,
)
from app.translator import (
    FusionPlanner,
    ImageTranslator,
    build_default_fusion_planner,
    build_default_translator,
    build_synthesis_prompt,
    build_translate_prompt,
    perturb_fusion_plan,
    redact_sensitive_text,
)

logger = logging.getLogger("style_translator.api")


def infer_mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"


def build_style_pack_export_zip(pack: StylePackModel) -> bytes:
    style_pack_payload = to_schema(pack).model_dump(mode="json")
    images: list[dict[str, str]] = []
    for asset in pack.assets:
        asset_path = Path(asset.path)
        archive_name = f"images/{asset.id}{asset_path.suffix or '.bin'}"
        images.append({"asset_id": asset.id, "path": archive_name, "mime_type": asset.mime_type})
    style_pack_payload["style_images"] = images

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("style_pack.json", json.dumps(style_pack_payload, indent=2))
        for asset, image_meta in zip(pack.assets, images, strict=False):
            zf.writestr(image_meta["path"], Path(asset.path).read_bytes())
    return buffer.getvalue()


def import_style_pack_archive(content: bytes, session: Session) -> StylePack:
    try:
        with zipfile.ZipFile(io.BytesIO(content), mode="r") as zf:
            if "style_pack.json" not in zf.namelist():
                raise HTTPException(status_code=400, detail="Archive is missing style_pack.json")
            exported = StylePack.model_validate(json.loads(zf.read("style_pack.json")))

            pack = StylePackModel(
                name=exported.name,
                version=exported.version,
                constraints_json=exported.constraints.model_dump_json(),
                prompt_anchors_json=exported.prompt_anchors.model_dump_json(),
            )
            session.add(pack)
            session.flush()

            base_dir = Path(settings.assets_dir) / str(pack.id)
            base_dir.mkdir(parents=True, exist_ok=True)

            for image in exported.style_images:
                if image.path not in zf.namelist():
                    raise HTTPException(status_code=400, detail=f"Archive is missing image: {image.path}")
                source_name = Path(image.path).name
                file_path = base_dir / source_name
                file_path.write_bytes(zf.read(image.path))
                session.add(
                    AssetModel(
                        style_pack_id=pack.id,
                        path=str(file_path),
                        mime_type=image.mime_type or infer_mime_type(file_path),
                    )
                )

            session.commit()
            session.refresh(pack)
            return to_schema(pack)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid zip archive") from exc


def default_constraints() -> Constraints:
    return Constraints(
        line_rules=["Preserve dominant edge rhythm"],
        composition_rules=["Maintain focal hierarchy"],
        translation_rules=["Map tones to nearest palette chip"],
        forbidden=["No watermark artifacts"],
    )


def default_prompt_anchors() -> PromptAnchors:
    return PromptAnchors(
        base_prompt="Preserve visual style and composition intent.",
        negative_prompt="avoid text overlays, avoid logos",
        variability_knobs=VariabilityKnobs(drift=0.2, density=0.5, abstraction=0.3),
    )


def validate_style_pack_id(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="style_pack_id must be a valid UUID") from exc


def parse_options(raw_options: str | None) -> TranslateOptions:
    if not raw_options:
        return TranslateOptions()
    try:
        return TranslateOptions.model_validate(json.loads(raw_options))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid options JSON: {exc}") from exc


def validate_image_uploads(images: list[UploadFile], request_id: str) -> list[tuple[UploadFile, bytes]]:
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required")
    validated: list[tuple[UploadFile, bytes]] = []
    for image in images:
        mime_type = image.content_type or ""
        if mime_type not in settings.allowed_image_mime_types:
            raise HTTPException(status_code=400, detail=f"Unsupported image mime type: {mime_type}")
        content = image.file.read()
        if len(content) > settings.effective_max_upload_bytes:
            raise HTTPException(status_code=413, detail="Image exceeds max upload size")
        validated.append((image, content))
    logger.info(json.dumps({"event": "validated_uploads", "request_id": request_id, "count": len(validated)}))
    return validated


def to_schema(model: StylePackModel) -> StylePack:
    constraints = Constraints.model_validate(json.loads(model.constraints_json))
    prompt_anchors = PromptAnchors.model_validate(json.loads(model.prompt_anchors_json))
    style_images = [StyleImageRef(asset_id=a.id, path=a.path, mime_type=a.mime_type) for a in model.assets]
    return StylePack(
        id=model.id,
        name=model.name,
        created_at=model.created_at,
        style_images=style_images,
        constraints=constraints,
        prompt_anchors=prompt_anchors,
        version=model.version,
    )


def to_job_schema(model: TranslationJobModel) -> TranslationJob:
    outputs = [
        JobOutput(
            image_base64=o.image_base64,
            fusion_plan=None if not o.fusion_plan_json else FusionPlan.model_validate(json.loads(o.fusion_plan_json)),
        )
        for o in model.outputs
    ]
    return TranslationJob(
        id=model.id,
        style_pack_id=model.style_pack_id,
        mode=model.mode,
        prompt_used=model.prompt_used,
        created_at=model.created_at,
        outputs=outputs,
    )


def get_analyzer() -> StylePackAnalyzer:
    return build_default_analyzer()


def get_translator() -> ImageTranslator:
    return build_default_translator()


def get_fusion_planner() -> FusionPlanner:
    return build_default_fusion_planner()


def execute_translation(
    session: Session,
    *,
    style_pack_id: str,
    mode: str,
    validated_images: list[tuple[str, bytes]],
    options: TranslateOptions,
    translator: ImageTranslator,
    fusion_planner: FusionPlanner,
) -> TranslateResponse:
    pack = session.get(StylePackModel, style_pack_id)
    if pack is None:
        raise RuntimeError("Style pack not found")
    style_pack = to_schema(pack)

    if mode == "translate_single":
        mime, content = validated_images[0]
        prompt_used = build_translate_prompt(style_pack, options)
        logger.info(
            json.dumps(
                {
                    "event": "final_prompt",
                    "mode": mode,
                    "style_pack_id": style_pack_id,
                    "prompt": redact_sensitive_text(prompt_used),
                }
            )
        )
        generated: list[str] = []
        for _ in range(options.variations):
            generated.extend(translator.translate_single(prompt_used, content, mime, options))
        return TranslateResponse(
            style_pack_id=style_pack_id,
            mode="translate_single",
            prompt_used=prompt_used,
            created_at=datetime.now(timezone.utc),
            images=[TranslationImage(image_base64=i) for i in generated],
        )

    image_inputs = [(content, mime) for mime, content in validated_images]
    base_plan = fusion_planner.generate_plan(image_inputs=image_inputs, options=options)
    outputs: list[TranslationImage] = []
    prompt_used = ""
    for idx in range(options.variations):
        plan = perturb_fusion_plan(base_plan, idx, len(validated_images))
        prompt_used = build_synthesis_prompt(style_pack, plan, options)
        logger.info(
            json.dumps(
                {
                    "event": "final_prompt",
                    "mode": mode,
                    "style_pack_id": style_pack_id,
                    "prompt": redact_sensitive_text(prompt_used),
                }
            )
        )
        anchor_mime, anchor_content = validated_images[plan.subject_from]
        generated = translator.translate_single(prompt_used, anchor_content, anchor_mime, options)
        outputs.extend([TranslationImage(image_base64=i, fusion_plan=plan) for i in generated])
    return TranslateResponse(
        style_pack_id=style_pack_id,
        mode="synthesize_multi",
        prompt_used=prompt_used,
        created_at=datetime.now(timezone.utc),
        images=outputs,
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Style Translator API", version="0.6.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(get_engine())

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="style-translator-api")

    @app.post("/style-packs", response_model=StylePack)
    async def create_style_pack(
        name: str = Form(..., min_length=1),
        images: list[UploadFile] = File(...),
        session: Session = Depends(get_session),
    ) -> StylePack:
        validated = validate_image_uploads(images, str(uuid4()))
        pack = StylePackModel(
            name=name,
            version="1.0.0",
            constraints_json=json.dumps(default_constraints().model_dump()),
            prompt_anchors_json=json.dumps(default_prompt_anchors().model_dump()),
        )
        session.add(pack)
        session.flush()
        base_dir = Path(settings.assets_dir) / str(pack.id)
        base_dir.mkdir(parents=True, exist_ok=True)
        for image, content in validated:
            file_path = base_dir / f"{uuid4()}{Path(image.filename or 'asset.bin').suffix or '.bin'}"
            file_path.write_bytes(content)
            session.add(AssetModel(style_pack_id=pack.id, path=str(file_path), mime_type=image.content_type or "application/octet-stream"))
        session.commit()
        session.refresh(pack)
        return to_schema(pack)

    @app.get("/style-packs", response_model=list[StylePack])
    def list_style_packs(session: Session = Depends(get_session)) -> list[StylePack]:
        return [to_schema(p) for p in session.query(StylePackModel).all()]

    @app.get("/style-packs/{style_pack_id}", response_model=StylePack)
    def get_style_pack(style_pack_id: str, session: Session = Depends(get_session)) -> StylePack:
        pack = session.get(StylePackModel, style_pack_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="Style pack not found")
        return to_schema(pack)

    @app.get("/style-packs/{style_pack_id}/export")
    def export_style_pack(style_pack_id: str, session: Session = Depends(get_session)) -> StreamingResponse:
        pack = session.get(StylePackModel, style_pack_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="Style pack not found")
        payload = build_style_pack_export_zip(pack)
        filename = f"style-pack-{pack.id}.zip"
        return StreamingResponse(
            io.BytesIO(payload),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/style-packs/import", response_model=StylePack)
    async def import_style_pack(
        archive: UploadFile = File(...),
        session: Session = Depends(get_session),
    ) -> StylePack:
        if (archive.content_type or "") not in {"application/zip", "application/x-zip-compressed", "multipart/x-zip"}:
            raise HTTPException(status_code=400, detail="Import file must be a zip archive")
        content = await archive.read()
        return import_style_pack_archive(content, session)

    @app.post("/style-packs/{style_pack_id}/analyze", response_model=StylePack)
    def analyze_style_pack(style_pack_id: str, session: Session = Depends(get_session), analyzer: StylePackAnalyzer = Depends(get_analyzer)) -> StylePack:
        pack = session.get(StylePackModel, style_pack_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="Style pack not found")
        constraints, prompt_anchors = analyze_with_retry(analyzer, [a.path for a in pack.assets])
        pack.constraints_json = json.dumps(constraints.model_dump())
        pack.prompt_anchors_json = json.dumps(prompt_anchors.model_dump())
        session.add(pack)
        session.commit()
        session.refresh(pack)
        return to_schema(pack)

    def persist_job_result(session: Session, job: TranslationJobModel, response: TranslateResponse) -> None:
        job.status = "completed"
        job.prompt_used = response.prompt_used
        job.result_json = response.model_dump_json()
        job.updated_at = datetime.now(timezone.utc)
        session.add(job)
        session.flush()
        for image in response.images:
            session.add(
                TranslationOutputModel(
                    job_id=job.id,
                    image_base64=image.image_base64,
                    fusion_plan_json=None if image.fusion_plan is None else image.fusion_plan.model_dump_json(),
                )
            )

    @app.post("/translate", response_model=TranslateResponse)
    def translate(
        style_pack_id: str = Form(...),
        mode: str = Form(...),
        input_images: list[UploadFile] = File(...),
        options: str | None = Form(default=None),
        session: Session = Depends(get_session),
        translator: ImageTranslator = Depends(get_translator),
        fusion_planner: FusionPlanner = Depends(get_fusion_planner),
    ) -> TranslateResponse:
        validated_id = validate_style_pack_id(style_pack_id)
        parsed_options = parse_options(options)
        validated_images = [(i.content_type or "image/png", c) for i, c in validate_image_uploads(input_images, str(uuid4()))]
        response = execute_translation(
            session,
            style_pack_id=validated_id,
            mode=mode,
            validated_images=validated_images,
            options=parsed_options,
            translator=translator,
            fusion_planner=fusion_planner,
        )
        job = TranslationJobModel(style_pack_id=validated_id, mode=mode, status="completed", prompt_used=response.prompt_used, result_json=response.model_dump_json())
        session.add(job)
        session.flush()
        for image in response.images:
            session.add(TranslationOutputModel(job_id=job.id, image_base64=image.image_base64, fusion_plan_json=None if image.fusion_plan is None else image.fusion_plan.model_dump_json()))
        session.commit()
        return response

    def run_translation_job(job_id: str, style_pack_id: str, mode: str, options: TranslateOptions, input_data: list[tuple[str, bytes]]) -> None:
        session = Session(get_engine())
        try:
            job = session.get(TranslationJobModel, job_id)
            if job is None:
                return
            job.status = "running"
            job.updated_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()

            response = execute_translation(
                session,
                style_pack_id=style_pack_id,
                mode=mode,
                validated_images=input_data,
                options=options,
                translator=build_default_translator(),
                fusion_planner=build_default_fusion_planner(),
            )
            job = session.get(TranslationJobModel, job_id)
            if job is None:
                return
            persist_job_result(session, job, response)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            job = session.get(TranslationJobModel, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)
                job.updated_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()
        finally:
            session.close()

    @app.post("/jobs/translate", response_model=CreateJobResponse)
    def create_translate_job(
        background_tasks: BackgroundTasks,
        style_pack_id: str = Form(...),
        mode: str = Form(...),
        input_images: list[UploadFile] = File(...),
        options: str | None = Form(default=None),
        session: Session = Depends(get_session),
    ) -> CreateJobResponse:
        validated_id = validate_style_pack_id(style_pack_id)
        parsed_options = parse_options(options)
        validated_images = validate_image_uploads(input_images, str(uuid4()))
        if mode == "synthesize_multi" and not (2 <= len(validated_images) <= 10):
            raise HTTPException(status_code=400, detail="synthesize_multi requires 2 to 10 input images")
        if mode == "translate_single" and len(validated_images) < 1:
            raise HTTPException(status_code=400, detail="translate_single requires at least 1 input image")

        job = TranslationJobModel(style_pack_id=validated_id, mode=mode, status="pending")
        session.add(job)
        session.commit()
        payload = [(image.content_type or "image/png", content) for image, content in validated_images]
        background_tasks.add_task(run_translation_job, job.id, validated_id, mode, parsed_options, payload)
        return CreateJobResponse(job_id=job.id)

    @app.get("/jobs/{job_id}", response_model=JobStatusResponse)
    def get_job(job_id: str, session: Session = Depends(get_session)) -> JobStatusResponse:
        job = session.get(TranslationJobModel, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        result = None
        if job.result_json:
            result = TranslateResponse.model_validate(json.loads(job.result_json))
        return JobStatusResponse(job_id=job.id, status=job.status, error_message=job.error_message, result=result)

    @app.get("/jobs", response_model=list[TranslationJob])
    def list_jobs(session: Session = Depends(get_session)) -> list[TranslationJob]:
        jobs = session.query(TranslationJobModel).order_by(TranslationJobModel.created_at.desc()).limit(50).all()
        return [to_job_schema(j) for j in jobs]

    return app


app = create_app()
