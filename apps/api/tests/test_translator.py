import pytest

from app.schemas import FusionPlan, PromptAnchors, StylePack, TranslateOptions, VariabilityKnobs
from app.translator import (
    build_synthesis_prompt,
    build_translate_prompt,
    enforce_style_lock,
    redact_sensitive_text,
    validate_fusion_plan_indices,
)


def make_style_pack() -> StylePack:
    return StylePack.model_validate(
        {
            "id": "pack-1",
            "name": "Pack",
            "created_at": "2025-01-01T00:00:00Z",
            "style_images": [],
            "constraints": {
                "line_rules": ["rule line"],
                "composition_rules": ["rule comp"],
                "translation_rules": ["rule trans"],
                "forbidden": ["forbidden thing"],
            },
            "prompt_anchors": {
                "base_prompt": "Base style prompt",
                "negative_prompt": "No text",
                "variability_knobs": {"drift": 0.2, "density": 0.3, "abstraction": 0.4},
            },
            "version": "1.0.0",
        }
    )


def make_unbounded_style_pack() -> StylePack:
    return StylePack.model_construct(
        id="pack-unsafe",
        name="Pack unsafe",
        created_at=make_style_pack().created_at,
        style_images=[],
        constraints=make_style_pack().constraints,
        prompt_anchors=PromptAnchors.model_construct(
            base_prompt="Base style prompt",
            negative_prompt="No text",
            variability_knobs=VariabilityKnobs.model_construct(drift=1.2, density=-0.1, abstraction=0.4),
        ),
        version="1.0.0",
    )


def test_enforce_style_lock_adds_rules_and_clamps_knobs() -> None:
    style_pack = make_unbounded_style_pack()

    locked = enforce_style_lock(style_pack, user_prompt_notes="note")

    assert "forbidden thing" in locked["forbidden"]
    assert "No hybridization" in locked["forbidden"]
    assert "No drift outside constraints" in locked["forbidden"]
    assert locked["variability"] == {"drift": 1.0, "density": 0.0, "abstraction": 0.4}


def test_build_translate_prompt_snapshot() -> None:
    prompt = build_translate_prompt(
        style_pack=make_style_pack(),
        options=TranslateOptions(
            size="1024x1024",
            quality="high",
            preserve_composition=True,
            variations=1,
            drift=0.6,
            density=0.7,
            abstraction=0.8,
        ),
        user_prompt_notes="keep symmetry",
    )

    expected = """Base style prompt
Style lock: No hybridization; no drift outside constraints.
Line rules: rule line
Composition rules: rule comp
Translation rules: rule trans
Forbidden: forbidden thing; No hybridization; No drift outside constraints
Preserve composition: True
Output size: 1024x1024
Output quality: high
Drift: 0.6; Density: 0.7; Abstraction: 0.8
Negative prompt: No text
User prompt notes: keep symmetry"""
    assert prompt == expected


def test_build_synthesis_prompt_snapshot() -> None:
    prompt = build_synthesis_prompt(
        style_pack=make_style_pack(),
        fusion_plan=FusionPlan(
            subject_from=0,
            background_from=1,
            motifs_from=[0, 1],
            composition_notes="keep subject centered",
            exclusions=["watermark"],
            dominance_weights=[0.7, 0.3],
        ),
        options=TranslateOptions(fusion_strategy="collage", variations=2),
        user_prompt_notes="prioritize framing",
    )

    expected = """Base style prompt
Style lock: No hybridization; no drift outside constraints.
Fusion strategy: collage
Fusion plan: {"subject_from":0,"background_from":1,"motifs_from":[0,1],"composition_notes":"keep subject centered","exclusions":["watermark"],"dominance_weights":[0.7,0.3]}
Line rules: rule line
Composition rules: rule comp
Translation rules: rule trans
Forbidden: forbidden thing; No hybridization; No drift outside constraints
Output size: 1024x1024
Output quality: high
Negative prompt: No text
User prompt notes: prioritize framing"""
    assert prompt == expected


def test_redact_sensitive_text_masks_keys_and_images() -> None:
    raw = "Authorization: Bearer sk-secret123 data:image/png;base64,abcd"
    redacted = redact_sensitive_text(raw)
    assert "sk-secret123" not in redacted
    assert "data:image/png;base64,abcd" not in redacted
    assert "[REDACTED" in redacted


def test_validate_fusion_plan_indices_rejects_out_of_range() -> None:
    plan = FusionPlan(
        subject_from=0,
        background_from=5,
        motifs_from=[1],
        composition_notes="note",
        exclusions=[],
        dominance_weights=[1.0],
    )
    with pytest.raises(ValueError):
        validate_fusion_plan_indices(plan, image_count=2)
