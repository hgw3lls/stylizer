# app/analyzer.py
from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Optional, Protocol, Set, Tuple
from urllib import error, request

from pydantic import ValidationError

from app.config import settings
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


# -------------------------
# Model auto-detection
# -------------------------

_MODELS_CACHE_TTL = int(os.getenv("OPENAI_MODELS_CACHE_TTL", "300"))
_models_cached_at: float = 0.0
_models_cached_ids: Optional[Set[str]] = None


def _get_api_key() -> str:
    key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return key


def _list_model_ids(force_refresh: bool = False) -> Set[str]:
    """Fetch available model IDs for this key via GET /v1/models."""
    global _models_cached_at, _models_cached_ids

    now = time.time()
    if (
        not force_refresh
        and _models_cached_ids is not None
        and (now - _models_cached_at) < _MODELS_CACHE_TTL
    ):
        return _models_cached_ids

    api_key = _get_api_key()
    url = f"{OPENAI_BASE_URL}/models"
    req = request.Request(
        url=url,
        method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"OpenAI /models error: {exc.code} {body}") from exc

    ids = {m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m}
    _models_cached_ids = ids
    _models_cached_at = now
    return ids


def _pick_first_available(ids: Set[str], preferred: list[str]) -> Optional[str]:
    for m in preferred:
        if m and (m in ids):
            return m
    return None


def auto_select_analysis_model(force_refresh: bool = False) -> str:
    """
    Choose an analysis-capable model that exists for this key.
    Prefer env/config override, then common fallbacks.
    """
    ids = _list_model_ids(force_refresh=force_refresh)

    override = (
        getattr(settings, "openai_analysis_model", None)
        or os.getenv("OPENAI_ANALYSIS_MODEL", "")
    )
    override = override.strip() if isinstance(override, str) else ""

    preferred = [
        override,
        "gpt-4o-mini",
        "gpt-4.1-mini",
        "gpt-4o",
        "gpt-4.1",
    ]
    chosen = _pick_first_available(ids, preferred)
    if chosen:
        return chosen

    # last resort: any gpt-* model
    gpts = sorted([m for m in ids if m.startswith("gpt-")])
    if not gpts:
        raise RuntimeError("No gpt-* models available to this API key/project.")
    return gpts[0]


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
        self.model = model or auto_select_analysis_model()

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
    configured = getattr(settings, "openai_analysis_model", None)
    model = configured.strip() if isinstance(configured, str) and configured.strip() else None
    return OpenAIStylePackAnalyzer(api_key=api_key, model=model)


def analyze_with_retry(analyzer: StylePackAnalyzer, image_paths: list[str]) -> Tuple[Constraints, PromptAnchors]:
    try:
        return analyzer.analyze(image_paths=image_paths)
    except (json.JSONDecodeError, KeyError, ValidationError) as first_error:
        return analyzer.analyze(image_paths=image_paths, validation_errors=str(first_error))
