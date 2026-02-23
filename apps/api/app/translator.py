import base64
import json
import re
from typing import Protocol
from urllib import error, request
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.config import settings
from app.model_select import select_analysis_model, select_image_model
from app.schemas import FusionPlan, StylePack, TranslateOptions

STYLE_LOCK_DIRECTIVE = "No hybridization; no drift outside constraints."
DEFAULT_FORBIDDEN = ["No hybridization", "No drift outside constraints"]
NO_IMAGE_MODEL_MESSAGE = (
    "No image generation model available for this API key/project. "
    "Set OPENAI_IMAGE_MODEL to an available model id or enable image models for this project."
)




def _encode_multipart_form_data(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----OpenAIBoundary{uuid4().hex}"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    for name, (filename, content, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def _is_responses_api_model_unsupported(error_body: str) -> bool:
    normalized = error_body.lower()
    return "not supported with the responses api" in normalized

def clamp_variability(value: float) -> float:
    return max(0.0, min(1.0, value))


def redact_sensitive_text(value: str) -> str:
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED]", value)
    redacted = re.sub(r"sk-[A-Za-z0-9]+", "[REDACTED_API_KEY]", redacted)
    redacted = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "[REDACTED_USER_IMAGE]", redacted)
    return redacted


def enforce_style_lock(style_pack: StylePack, user_prompt_notes: str | None = None) -> dict[str, object]:
    forbidden = list(style_pack.constraints.forbidden)
    for item in DEFAULT_FORBIDDEN:
        if item not in forbidden:
            forbidden.append(item)

    variability = {
        "drift": clamp_variability(style_pack.prompt_anchors.variability_knobs.drift),
        "density": clamp_variability(style_pack.prompt_anchors.variability_knobs.density),
        "abstraction": clamp_variability(style_pack.prompt_anchors.variability_knobs.abstraction),
    }

    return {
        "forbidden": forbidden,
        "style_lock": STYLE_LOCK_DIRECTIVE,
        "variability": variability,
        "user_prompt_notes": redact_sensitive_text(user_prompt_notes or "").strip(),
    }


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


def build_translate_prompt(style_pack: StylePack, options: TranslateOptions, user_prompt_notes: str | None = None) -> str:
    lock = enforce_style_lock(style_pack, user_prompt_notes=user_prompt_notes)
    line_rules = "; ".join(style_pack.constraints.line_rules)
    composition_rules = "; ".join(style_pack.constraints.composition_rules)
    translation_rules = "; ".join(style_pack.constraints.translation_rules)
    forbidden = "; ".join(lock["forbidden"])

    drift = clamp_variability(options.drift if options.drift is not None else lock["variability"]["drift"])
    density = clamp_variability(options.density if options.density is not None else lock["variability"]["density"])
    abstraction = clamp_variability(options.abstraction if options.abstraction is not None else lock["variability"]["abstraction"])

    prompt = (
        f"{style_pack.prompt_anchors.base_prompt}\n"
        f"Style lock: {lock['style_lock']}\n"
        f"Line rules: {line_rules}\n"
        f"Composition rules: {composition_rules}\n"
        f"Translation rules: {translation_rules}\n"
        f"Forbidden: {forbidden}\n"
        f"Preserve composition: {options.preserve_composition}\n"
        f"Output size: {options.size}\n"
        f"Output quality: {options.quality}\n"
        f"Drift: {drift}; Density: {density}; Abstraction: {abstraction}\n"
        f"Negative prompt: {style_pack.prompt_anchors.negative_prompt}"
    )
    if lock["user_prompt_notes"]:
        prompt = f"{prompt}\nUser prompt notes: {lock['user_prompt_notes']}"
    return prompt


def build_synthesis_prompt(
    style_pack: StylePack,
    fusion_plan: FusionPlan,
    options: TranslateOptions,
    user_prompt_notes: str | None = None,
) -> str:
    lock = enforce_style_lock(style_pack, user_prompt_notes=user_prompt_notes)
    prompt = (
        f"{style_pack.prompt_anchors.base_prompt}\n"
        f"Style lock: {lock['style_lock']}\n"
        f"Fusion strategy: {options.fusion_strategy}\n"
        f"Fusion plan: {fusion_plan.model_dump_json()}\n"
        f"Line rules: {'; '.join(style_pack.constraints.line_rules)}\n"
        f"Composition rules: {'; '.join(style_pack.constraints.composition_rules)}\n"
        f"Translation rules: {'; '.join(style_pack.constraints.translation_rules)}\n"
        f"Forbidden: {'; '.join(lock['forbidden'])}\n"
        f"Output size: {options.size}\n"
        f"Output quality: {options.quality}\n"
        f"Negative prompt: {style_pack.prompt_anchors.negative_prompt}"
    )
    if lock["user_prompt_notes"]:
        prompt = f"{prompt}\nUser prompt notes: {lock['user_prompt_notes']}"
    return prompt


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
        selected_model = select_image_model()
        if not selected_model:
            raise HTTPException(status_code=503, detail=NO_IMAGE_MODEL_MESSAGE)
        b64_input = base64.b64encode(source_image).decode("utf-8")
        payload = {
            "model": selected_model,
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
            images: list[str] = []
            for output in data.get("output", []):
                for item in output.get("content", []):
                    if item.get("type") in {"output_image", "image"} and item.get("image_base64"):
                        images.append(item["image_base64"])
            if images:
                return images
            raise RuntimeError("OpenAI response did not return generated images")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            if exc.code != 400 or not _is_responses_api_model_unsupported(body):
                raise RuntimeError(f"OpenAI image generation failed: {exc.code} {body}") from exc

        form_fields = {
            "model": selected_model,
            "prompt": prompt,
            "size": options.size,
            "quality": options.quality,
            "response_format": "b64_json",
        }
        if options.seed is not None:
            form_fields["seed"] = str(options.seed)
        form_body, content_type = _encode_multipart_form_data(
            fields=form_fields,
            files={"image": ("input.png", source_image, source_mime_type)},
        )
        fallback_req = request.Request(
            url="https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": content_type},
            data=form_body,
            method="POST",
        )

        try:
            with request.urlopen(fallback_req, timeout=90) as resp:
                fallback_data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"OpenAI image generation failed: {exc.code} {body}") from exc

        images = [item.get("b64_json") for item in fallback_data.get("data", []) if item.get("b64_json")]
        if not images:
            raise RuntimeError("OpenAI images edits response did not return generated images")
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
    model = select_image_model()
    if not model:
        raise HTTPException(status_code=503, detail=NO_IMAGE_MODEL_MESSAGE)
    return OpenAIImageTranslator(api_key=settings.openai_api_key, model=model)


def build_default_fusion_planner() -> FusionPlanner:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for fusion planning")
    return OpenAIFusionPlanner(api_key=settings.openai_api_key, model=select_analysis_model())
