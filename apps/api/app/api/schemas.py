from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.image_jobs import (
    AspectRatio,
    EditFitMode,
    ImageJobOperation,
    ImageJobStatus,
    ImageMimeType,
    ImageProgressPhase,
    ImageProgressSource,
    ImageProviderName,
    ImageStyle,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: Literal["canvasrelay-api"]
    version: str
    demo_mode: bool = Field(alias="demoMode")
    timestamp: datetime


class ImageJobCreate(ApiModel):
    prompt: str = Field(min_length=1, max_length=1200)
    aspect_ratio: AspectRatio = Field(alias="aspectRatio")
    style: ImageStyle
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)

    @field_validator("prompt")
    @classmethod
    def validate_prompt_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt must include visible text.")
        return value


class ImageJobSettings(ApiModel):
    aspect_ratio: AspectRatio = Field(alias="aspectRatio")
    style: ImageStyle
    seed: int
    provider: ImageProviderName
    operation: ImageJobOperation
    has_face_reference: bool = Field(alias="hasFaceReference")
    source_job_id: str | None = Field(default=None, alias="sourceJobId")
    edit: ImageEditSettingsResponse | None = None


class LoraSelectionResponse(ApiModel):
    id: str
    model_weight: float = Field(alias="modelWeight")
    clip_weight: float = Field(alias="clipWeight")


class ImageEditSettingsResponse(ApiModel):
    steps: int
    cfg: float
    reference_influence: float = Field(alias="referenceInfluence")
    grounding_resolution: int = Field(alias="groundingResolution")
    fit_mode: EditFitMode = Field(alias="fitMode")
    sampler: str
    scheduler: str
    loras: list[LoraSelectionResponse]


class ImageJobResult(ApiModel):
    url: str
    mime_type: ImageMimeType = Field(alias="mimeType")
    width: int
    height: int


class ImageJobError(ApiModel):
    code: str
    message: str
    action: str
    retryable: bool


class ImageJobResponse(ApiModel):
    id: str
    status: ImageJobStatus
    progress: int | None = Field(ge=0, le=100)
    phase: ImageProgressPhase
    current_step: int | None = Field(default=None, alias="currentStep", ge=0)
    total_steps: int | None = Field(default=None, alias="totalSteps", ge=1)
    progress_source: ImageProgressSource = Field(alias="progressSource")
    stalled: bool
    estimated_remaining_seconds: int | None = Field(
        default=None, alias="estimatedRemainingSeconds", ge=0
    )
    prompt: str
    settings: ImageJobSettings
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(alias="startedAt")
    completed_at: datetime | None = Field(alias="completedAt")
    result: ImageJobResult | None
    error: ImageJobError | None


class ImageJobListResponse(ApiModel):
    items: list[ImageJobResponse]


class ImageProviderResponse(ApiModel):
    provider: ImageProviderName
    mode: Literal["demo", "live"]
    label: str
    ready: bool
    message: str


class ImageEditLoraOption(ApiModel):
    id: str
    label: str


class ImageEditOptionDefaults(ApiModel):
    steps: int
    cfg: float
    sampler: str
    scheduler: str


class ImageEditProviderOptionsResponse(ApiModel):
    samplers: list[str]
    schedulers: list[str]
    loras: list[ImageEditLoraOption]
    defaults: ImageEditOptionDefaults
