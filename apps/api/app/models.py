from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class StylePackModel(Base):
    __tablename__ = "style_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    constraints_json: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_anchors_json: Mapped[str] = mapped_column(Text, nullable=False)

    assets: Mapped[list["AssetModel"]] = relationship(back_populates="style_pack", cascade="all, delete-orphan")
    jobs: Mapped[list["TranslationJobModel"]] = relationship(back_populates="style_pack", cascade="all, delete-orphan")


class AssetModel(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    style_pack_id: Mapped[str] = mapped_column(String(36), ForeignKey("style_packs.id"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)

    style_pack: Mapped[StylePackModel] = relationship(back_populates="assets")


class TranslationJobModel(Base):
    __tablename__ = "translation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    style_pack_id: Mapped[str] = mapped_column(String(36), ForeignKey("style_packs.id"), nullable=False)
    mode: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    prompt_used: Mapped[str] = mapped_column(Text, default="", nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    style_pack: Mapped[StylePackModel] = relationship(back_populates="jobs")
    outputs: Mapped[list["TranslationOutputModel"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class TranslationOutputModel(Base):
    __tablename__ = "translation_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("translation_jobs.id"), nullable=False)
    image_base64: Mapped[str] = mapped_column(Text, nullable=False)
    fusion_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[TranslationJobModel] = relationship(back_populates="outputs")
