import pytest

from app.schemas import Constraints, FusionPlan, PromptAnchors, TranslateOptions, VariabilityKnobs
from app.translator import build_synthesis_prompt, build_translate_prompt, validate_fusion_plan_indices


def test_build_translate_prompt_includes_style_and_options() -> None:
    prompt = build_translate_prompt(
        prompt_anchors=PromptAnchors(
            base_prompt="Base style prompt",
            negative_prompt="No text",
            variability_knobs=VariabilityKnobs(drift=0.2, density=0.3, abstraction=0.4),
        ),
        constraints=Constraints(
            line_rules=["rule line"],
            composition_rules=["rule comp"],
            translation_rules=["rule trans"],
            forbidden=["forbidden thing"],
        ),
        options=TranslateOptions(
            size="1024x1024",
            quality="high",
            preserve_composition=True,
            variations=1,
            drift=0.6,
            density=0.7,
            abstraction=0.8,
        ),
    )

    assert "Base style prompt" in prompt
    assert "rule line" in prompt
    assert "rule comp" in prompt
    assert "rule trans" in prompt
    assert "forbidden thing" in prompt
    assert "Preserve composition: True" in prompt
    assert "Drift: 0.6; Density: 0.7; Abstraction: 0.8" in prompt


def test_build_synthesis_prompt_includes_fusion_plan() -> None:
    prompt = build_synthesis_prompt(
        base_prompt="Synth base",
        constraints=Constraints(
            line_rules=["line"],
            composition_rules=["composition"],
            translation_rules=["translate"],
            forbidden=["forbidden"],
        ),
        fusion_plan=FusionPlan(
            subject_from=0,
            background_from=1,
            motifs_from=[0, 1],
            composition_notes="keep subject centered",
            exclusions=["watermark"],
            dominance_weights=[0.7, 0.3],
        ),
        options=TranslateOptions(fusion_strategy="collage", variations=2),
    )

    assert "Synth base" in prompt
    assert "Fusion strategy: collage" in prompt
    assert '"subject_from":0' in prompt
    assert "line" in prompt


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
