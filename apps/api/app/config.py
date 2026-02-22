from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str = "sqlite:///./style_translator.db"
    assets_root: str = "data/assets"
    openai_api_key: str = ""
    openai_analysis_model: str = "gpt-4.1-mini"
    openai_image_model: str = "gpt-image-1"
    max_upload_bytes: int = 10_485_760
    allowed_image_mime_types: list[str] = ["image/png", "image/jpeg", "image/webp"]

    model_config = SettingsConfigDict(env_file="../../.env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_image_mime_types", mode="before")
    @classmethod
    def parse_mime_types(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("assets_root", mode="before")
    @classmethod
    def normalize_assets_root(cls, value: str) -> str:
        return str(Path(value))


settings = Settings()
