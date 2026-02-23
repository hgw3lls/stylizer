from __future__ import annotations

import json
from typing import Any, List, Optional

from pydantic import field_validator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application settings loaded from .env (pydantic-settings v2).
    This file intentionally defines ALL fields used across the app so
    FastAPI doesn't crash on missing attributes.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    database_url: str = "sqlite:///./data/app.db"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    api_cors_origins: List[str] = ["http://localhost:5173"]

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                return json.loads(s)
            return [item.strip() for item in s.split(",") if item.strip()]
        raise TypeError("api_cors_origins must be list or string")

    # ------------------------------------------------------------------
    # Upload / Image Validation
    # ------------------------------------------------------------------
    allowed_image_mime_types: List[str] = [
        "image/png",
        "image/jpeg",
        "image/webp",
    ]

    max_upload_mb: int = 25
    max_upload_bytes: Optional[int] = None

    @computed_field
    @property
    def effective_max_upload_bytes(self) -> int:
        return int(self.max_upload_bytes or (self.max_upload_mb * 1024 * 1024))

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    storage_dir: str = "./data"
    assets_dir: str = "./data/assets"
    assets_root: str = "./data/assets"
    stylepacks_dir: str = "./data/stylepacks"

    # ------------------------------------------------------------------
    # OpenAI
    # ------------------------------------------------------------------
    openai_api_key: Optional[str] = "REDACTED_OPENAI_KEY"
    openai_image_model: str = "gpt-image-1.5"
    openai_analysis_model: str = "gpt-4o-mini"
    # ------------------------------------------------------------------
    # Style / Generation Defaults
    # ------------------------------------------------------------------
    default_variations: int = 1
    max_variations: int = 6

    default_drift: float = 0.2
    default_density: float = 0.4
    default_abstraction: float = 0.5

    # ------------------------------------------------------------------
    # Debug / Dev
    # ------------------------------------------------------------------
    debug: bool = True


settings = Settings()
