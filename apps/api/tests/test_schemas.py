from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import Constraints, PromptAnchors, StyleImageRef, StylePack, VariabilityKnobs


def test_style_pack_rejects_unknown_fields() -> None:
    payload = {
        "id": "sp-1",
        "name": "Pack",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "style_images": [
            {"asset_id": "a1", "path": "data/assets/sp-1/a1.png", "mime_type": "image/png"}
        ],
        "constraints": {
            "line_rules": ["keep curves"],
            "composition_rules": ["centered"],
            "translation_rules": ["reduce noise"],
            "forbidden": ["text"],
            "unknown": ["x"],
        },
        "prompt_anchors": {
            "base_prompt": "base",
            "negative_prompt": "neg",
            "variability_knobs": {"drift": 0.1, "density": 0.2, "abstraction": 0.3},
        },
        "version": "1.2.3",
    }

    with pytest.raises(ValidationError):
        StylePack.model_validate(payload)


def test_style_pack_valid_payload() -> None:
    pack = StylePack(
        id="sp-1",
        name="Pack",
        created_at=datetime.now(timezone.utc),
        style_images=[StyleImageRef(asset_id="a1", path="data/assets/sp-1/a1.png", mime_type="image/png")],
        constraints=Constraints(
            line_rules=["keep curves"],
            composition_rules=["centered"],
            translation_rules=["reduce noise"],
            forbidden=["text"],
        ),
        prompt_anchors=PromptAnchors(
            base_prompt="base",
            negative_prompt="neg",
            variability_knobs=VariabilityKnobs(drift=0.1, density=0.2, abstraction=0.3),
        ),
        version="1.2.3",
    )

    assert pack.version == "1.2.3"
