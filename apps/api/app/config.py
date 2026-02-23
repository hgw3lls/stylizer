from __future__ import annotations

import json
import math
from typing import Any, List, Optional

from pydantic import AliasChoices, Field, computed_field, field_validator, model_validator
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
    # Runtime / app metadata
    # ------------------------------------------------------------------
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

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
    legacy_max_upload_bytes: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("legacy_max_upload_bytes", "MAX_UPLOAD_BYTES"),
    )

    @model_validator(mode="after")
    def apply_legacy_upload_size(self) -> "Settings":
        # Back-compat: if MAX_UPLOAD_BYTES is provided, map to MB unless explicitly set.
        if self.legacy_max_upload_bytes and self.legacy_max_upload_bytes > 0:
            self.max_upload_mb = max(1, math.ceil(self.legacy_max_upload_bytes / (1024 * 1024)))
        return self

    @computed_field
    @property
    def max_upload_bytes(self) -> int:
        # Canonical bytes value derived from max_upload_mb.
        return int(self.max_upload_mb * 1024 * 1024)

    @computed_field
    @property
    def effective_max_upload_bytes(self) -> int:
        # Backward-compatible alias used by existing call sites.
        return self.max_upload_bytes

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------
    storage_dir: str = "./data"
    assets_dir: str = Field(
        default="./data/assets",
        validation_alias=AliasChoices("assets_dir", "ASSETS_DIR", "ASSETS_ROOT"),
    )
    stylepacks_dir: str = "./data/stylepacks"

    @computed_field
    @property
    def assets_root(self) -> str:
        # Back-compat alias: old name points to canonical assets_dir.
        return self.assets_dir

    # ------------------------------------------------------------------
    # OpenAI
    # ------------------------------------------------------------------
    openai_api_key: Optional[str] = None
    openai_image_model: str = "gpt-image-1"
    openai_analysis_model: str = ""
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
    debug: bool = False


settings = Settings()
