import base64
import json
from typing import Protocol
from urllib import error, request

from pydantic import ValidationError

from app.config import settings
from app.schemas import Constraints, FusionPlan, PromptAnchors, TranslateOptions

FUSION_PLAN_PROMPT = """
You are a style fusion planner. Analyze multiple input images and return JSON only.
Return valid JSON matching exactly:
{
  "subject_from": 0,
  "background_from": 1,
  "motifs_from": [0,2],
  "composition_notes": "...",
  "exclusions": ["..."],
  "dominance_weights": [0.6,0.4]
}
Rules:
- No prose, no markdown.
- No extra keys.
- Indices must reference provided input images (0-based).
""".strip()


def build_translate_prompt(
    prompt_anchors: PromptAnchors,
    constraints: Constraints,
    options: TranslateOptions,
) -> str:
    line_rules = "; ".join(constraints.line_rules)
    composition_rules = "; ".join(constraints.composition_rules)
    translation_rules = "; ".join(constraints.translation_rules)
    forbidden = "; ".join(constraints.forbidden)

    drift = options.drift if options.drift is not None else prompt_anchors.variability_knobs.drift
    density = options.density if options.density is not None else prompt_anchors.variability_knobs.density
    abstraction = options.abstraction if options.abstraction is not None else prompt_anchors.variability_knobs.abstraction

    return (
        f"{prompt_anchors.base_prompt}\n"
        f"Line rules: {line_rules}\n"
        f"Composition rules: {composition_rules}\n"
        f"Translation rules: {translation_rules}\n"
        f"Forbidden: {forbidden}\n"
        f"Preserve composition: {options.preserve_composition}\n"
        f"Output size: {options.size}\n"
        f"Output quality: {options.quality}\n"
        f"Drift: {drift}; Density: {density}; Abstraction: {abstraction}\n"
        f"Negative prompt: {prompt_anchors.negative_prompt}"
    )


def build_synthesis_prompt(
    base_prompt: str,
    constraints: Constraints,
    fusion_plan: FusionPlan,
    options: TranslateOptions,
) -> str:
    return (
        f"{base_prompt}\n"
        f"Fusion strategy: {options.fusion_strategy}\n"
        f"Fusion plan: {fusion_plan.model_dump_json()}\n"
        f"Line rules: {'; '.join(constraints.line_rules)}\n"
        f"Composition rules: {'; '.join(constraints.composition_rules)}\n"
        f"Translation rules: {'; '.join(constraints.translation_rules)}\n"
        f"Forbidden: {'; '.join(constraints.forbidden)}\n"
        f"Output size: {options.size}\n"
        f"Output quality: {options.quality}"
    )


def validate_fusion_plan_indices(plan: FusionPlan, image_count: int) -> None:
    idxs = [plan.subject_from, plan.background_from, *plan.motifs_from]
    for idx in idxs:
        if idx < 0 or idx >= image_count:
            raise ValueError(f"Fusion plan index out of range: {idx} for {image_count} images")


class ImageTranslator(Protocol):
    def translate_single(
        self,
        prompt: str,
        source_image: bytes,
        source_mime_type: str,
        options: TranslateOptions,
    ) -> list[str]: ...


class FusionPlanner(Protocol):
    def generate_plan(self, image_inputs: list[tuple[bytes, str]], options: TranslateOptions) -> FusionPlan: ...


class OpenAIImageTranslator:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def translate_single(
        self,
        prompt: str,
        source_image: bytes,
        source_mime_type: str,
        options: TranslateOptions,
    ) -> list[str]:
        b64_input = base64.b64encode(source_image).decode("utf-8")
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": f"data:{source_mime_type};base64,{b64_input}"},
                    ],
                }
            ],
            "tools": [{"type": "image_generation", "size": options.size, "quality": options.quality}],
        }
        if options.seed is not None:
            payload["seed"] = options.seed

        req = request.Request(
            url="https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI image generation failed: {exc.code} {body}") from exc

        images: list[str] = []
        for output in data.get("output", []):
            for item in output.get("content", []):
                if item.get("type") in {"output_image", "image"} and item.get("image_base64"):
                    images.append(item["image_base64"])
        if not images:
            raise RuntimeError("OpenAI response did not return generated images")
        return images


class OpenAIFusionPlanner:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def generate_plan(self, image_inputs: list[tuple[bytes, str]], options: TranslateOptions) -> FusionPlan:
        content: list[dict[str, str]] = [
            {
                "type": "input_text",
                "text": f"Generate a fusion plan for strategy={options.fusion_strategy}. Return JSON only with no extra keys.",
            }
        ]
        for b, mime in image_inputs:
            content.append(
                {"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(b).decode('utf-8')}"}
            )

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": FUSION_PLAN_PROMPT}]},
                {"role": "user", "content": content},
            ],
        }
        req = request.Request(
            url="https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI fusion planning failed: {exc.code} {body}") from exc

        text = data.get("output_text")
        if not text:
            raise RuntimeError("Fusion plan response missing output_text")
        try:
            plan = FusionPlan.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(f"Invalid fusion plan JSON: {exc}") from exc
        validate_fusion_plan_indices(plan, len(image_inputs))
        return plan


def perturb_fusion_plan(base: FusionPlan, variant_index: int, image_count: int) -> FusionPlan:
    motifs = base.motifs_from[:]
    if motifs and variant_index % 2 == 1:
        motifs = motifs[:-1]
    weights = base.dominance_weights[:]
    if weights:
        weights[0] = max(0.0, min(1.0, weights[0] - (0.05 * variant_index)))
    note = f"{base.composition_notes}; variant={variant_index}; adjust framing and crop subtly"
    plan = FusionPlan(
        subject_from=base.subject_from,
        background_from=base.background_from,
        motifs_from=motifs,
        composition_notes=note,
        exclusions=base.exclusions,
        dominance_weights=weights or [1.0],
    )
    validate_fusion_plan_indices(plan, image_count)
    return plan


def build_default_translator() -> ImageTranslator:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for translation")
    return OpenAIImageTranslator(api_key=settings.openai_api_key, model=settings.openai_image_model)


def build_default_fusion_planner() -> FusionPlanner:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for fusion planning")
    return OpenAIFusionPlanner(api_key=settings.openai_api_key, model=settings.openai_analysis_model)
