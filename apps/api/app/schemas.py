from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StyleImageRef(StrictModel):
    asset_id: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    mime_type: str = Field(..., min_length=1)


class Constraints(StrictModel):
    palette: list[str] | None = None
    materials: list[str] | None = None
    line_rules: list[str] = Field(default_factory=list)
    composition_rules: list[str] = Field(default_factory=list)
    translation_rules: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class VariabilityKnobs(StrictModel):
    drift: float = Field(..., ge=0, le=1)
    density: float = Field(..., ge=0, le=1)
    abstraction: float = Field(..., ge=0, le=1)


class PromptAnchors(StrictModel):
    base_prompt: str
    negative_prompt: str
    variability_knobs: VariabilityKnobs


class StylePack(StrictModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    created_at: datetime
    style_images: list[StyleImageRef] = Field(default_factory=list)
    constraints: Constraints
    prompt_anchors: PromptAnchors
    version: str = Field(
        ...,
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$",
    )


class TranslateOptions(StrictModel):
    size: str = "1024x1024"
    quality: str = "high"
    seed: int | None = None
    variations: int = Field(default=1, ge=1, le=6)
    preserve_composition: bool = True
    drift: float | None = Field(default=None, ge=0, le=1)
    density: float | None = Field(default=None, ge=0, le=1)
    abstraction: float | None = Field(default=None, ge=0, le=1)
    dominance_weights: list[float] | None = None
    fusion_strategy: Literal["collage", "poseA_bgB", "motif_fusion"] | None = None


class FusionPlan(StrictModel):
    subject_from: int = Field(..., ge=0)
    background_from: int = Field(..., ge=0)
    motifs_from: list[int] = Field(default_factory=list)
    composition_notes: str
    exclusions: list[str] = Field(default_factory=list)
    dominance_weights: list[float] = Field(default_factory=list)


class TranslationImage(StrictModel):
    image_base64: str
    fusion_plan: FusionPlan | None = None


class TranslateResponse(StrictModel):
    style_pack_id: str
    mode: Literal["translate_single", "synthesize_multi"]
    prompt_used: str
    created_at: datetime
    images: list[TranslationImage]


class JobOutput(StrictModel):
    image_base64: str
    fusion_plan: FusionPlan | None = None


class TranslationJob(StrictModel):
    id: str
    style_pack_id: str
    mode: str
    prompt_used: str
    created_at: datetime
    outputs: list[JobOutput]


class HealthResponse(StrictModel):
    status: str
    service: str


class CreateJobResponse(StrictModel):
    job_id: str


class JobStatusResponse(StrictModel):
    job_id: str
    status: str
    error_message: str | None = None
    result: TranslateResponse | None = None
