# app/analyzer.py
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Optional, Protocol, Tuple
from urllib import error, request

from pydantic import ValidationError

from app.config import settings
from app.model_select import select_analysis_model
from app.schemas import Constraints, PromptAnchors

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


STYLE_PACK_ANALYSIS_SYSTEM = """
You analyze style reference images and produce a strict JSON spec.

Return valid JSON only. No markdown, no prose, no extra keys.

The JSON MUST match exactly this shape:

{
  "constraints": {
    "palette": ["...optional strings..."],
    "materials": ["...optional strings..."],
    "line_rules": ["...strings..."],
    "composition_rules": ["...strings..."],
    "translation_rules": ["...strings..."],
    "forbidden": ["...strings..."]
  },
  "prompt_anchors": {
    "base_prompt": "...",
    "negative_prompt": "...",
    "variability_knobs": {
      "drift": 0.0,
      "density": 0.0,
      "abstraction": 0.0
    }
  }
}

Rules:
- JSON must be syntactically valid.
- All required keys must exist.
- variability_knobs values must be numbers in [0, 1].
- No extra keys at any level.
""".strip()


class StylePackAnalyzer(Protocol):
    def analyze(
        self, image_paths: list[str], validation_errors: Optional[str] = None
    ) -> Tuple[Constraints, PromptAnchors]:
        ...


def _get_api_key() -> str:
    key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return key


# -------------------------
# Image encoding helpers
# -------------------------

def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _file_to_data_url(path: Path) -> str:
    b = path.read_bytes()
    mime = _guess_mime(path)
    b64 = base64.b64encode(b).decode("ascii")
    return f"data:{mime};base64,{b64}"


# -------------------------
# Analyzer implementation
# -------------------------

class OpenAIStylePackAnalyzer:
    def __init__(self, api_key: str, model: Optional[str] = None) -> None:
        self.api_key = api_key
        self.model = model or select_analysis_model()

    def analyze(
        self, image_paths: list[str], validation_errors: Optional[str] = None
    ) -> Tuple[Constraints, PromptAnchors]:
        raw = self._call_openai(image_paths=image_paths, validation_errors=validation_errors)
        parsed = json.loads(raw)
        constraints = Constraints.model_validate(parsed["constraints"])
        prompt_anchors = PromptAnchors.model_validate(parsed["prompt_anchors"])
        return constraints, prompt_anchors

    def _call_openai(self, image_paths: list[str], validation_errors: Optional[str] = None) -> str:
        retry_hint = ""
        if validation_errors:
            retry_hint = (
                "\nPrevious output failed validation. Fix these errors exactly:\n"
                f"{validation_errors}\n"
            )

        user_text = (
            "Analyze the attached style reference images and return only the required JSON object. "
            "Use the images as the sole style sources."
            f"{retry_hint}"
        )

        content = [{"type": "input_text", "text": user_text}]

        for p in image_paths:
            path = Path(p).resolve()
            if not path.exists():
                raise RuntimeError(f"Style image not found: {path}")
            content.append(
                {"type": "input_image", "image_url": _file_to_data_url(path), "detail": "auto"}
            )

        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": STYLE_PACK_ANALYSIS_SYSTEM}],
                },
                {"role": "user", "content": content},
            ],
        }

        req = request.Request(
            url=f"{OPENAI_BASE_URL}/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise RuntimeError(f"OpenAI API error: {exc.code} {body}") from exc

        # Preferred: output_text
        out_text = data.get("output_text")
        if isinstance(out_text, str) and out_text.strip():
            return out_text

        # Fallback: scan output items
        output = data.get("output") or []
        for item in output:
            for c in (item.get("content") or []):
                t = c.get("text")
                if isinstance(t, str) and t.strip():
                    return t

        raise RuntimeError("OpenAI response did not include any output text.")


def build_default_analyzer() -> StylePackAnalyzer:
    api_key = _get_api_key()
    return OpenAIStylePackAnalyzer(api_key=api_key, model=select_analysis_model())


def analyze_with_retry(analyzer: StylePackAnalyzer, image_paths: list[str]) -> Tuple[Constraints, PromptAnchors]:
    try:
        return analyzer.analyze(image_paths=image_paths)
    except (json.JSONDecodeError, KeyError, ValidationError) as first_error:
        return analyzer.analyze(image_paths=image_paths, validation_errors=str(first_error))
