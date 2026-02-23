from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Set
from urllib import request, error


OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


@dataclass(frozen=True)
class ModelSelection:
    analysis_model: str
    image_model: Optional[str]  # None if your key has no image models


# Simple TTL cache (process-level)
_CACHE_TTL_SECONDS = int(os.getenv("OPENAI_MODELS_CACHE_TTL", "300"))
_cached_at: float = 0.0
_cached_ids: Optional[Set[str]] = None


def _get_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return key


def list_model_ids(force_refresh: bool = False) -> Set[str]:
    """Return the set of model ids available to the current API key."""
    global _cached_at, _cached_ids

    now = time.time()
    if not force_refresh and _cached_ids is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return _cached_ids

    url = f"{OPENAI_BASE_URL}/models"
    req = request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {_get_api_key()}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"OpenAI /models failed: {exc.code} {detail}") from exc

    data = json.loads(body)
    ids = {m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m}

    _cached_ids = ids
    _cached_at = now
    return ids


def _pick_first_available(ids: Set[str], preferred: list[str]) -> Optional[str]:
    for m in preferred:
        if m in ids:
            return m
    return None


def auto_select_models(force_refresh: bool = False) -> ModelSelection:
    """
    Pick best available analysis + image model for this key.

    Notes:
    - The image generation guide/API supports GPT Image and DALL·E model IDs,
      but availability is per-account/project. :contentReference[oaicite:1]{index=1}
    """
    ids = list_model_ids(force_refresh=force_refresh)

    # ---- Analysis/text model preferences ----
    # Choose conservative, widely available options first.
    analysis_preferred = [
        os.getenv("OPENAI_ANALYSIS_MODEL", "").strip(),  # allow override
        "gpt-4o-mini",
        "gpt-4.1-mini",
        "gpt-4o",
        "gpt-4.1",
    ]
    analysis_preferred = [m for m in analysis_preferred if m]  # drop empties
    analysis_model = _pick_first_available(ids, analysis_preferred)
    if not analysis_model:
        # last resort: pick *any* gpt model id (best-effort)
        fallback = sorted([m for m in ids if m.startswith("gpt-")])
        if not fallback:
            raise RuntimeError("No GPT models available to this key (check project/key).")
        analysis_model = fallback[0]

    # ---- Image model preferences ----
    # Model IDs listed in the Images reference (availability varies by org/project). :contentReference[oaicite:2]{index=2}
    image_preferred = [
        os.getenv("OPENAI_IMAGE_MODEL", "").strip(),  # allow override
        "gpt-image-1.5",
        "gpt-image-1",
        "gpt-image-1-mini",
        "dall-e-3",
        "dall-e-2",
    ]
    image_preferred = [m for m in image_preferred if m]
    image_model = _pick_first_available(ids, image_preferred)

    # If none available, return None (your UI can disable generation gracefully)
    return ModelSelection(analysis_model=analysis_model, image_model=image_model)
