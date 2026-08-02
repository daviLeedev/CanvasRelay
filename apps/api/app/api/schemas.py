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


class LoraSelectionInput(ApiModel):
    id: str = Field(min_length=1, max_length=128)
    model_weight: float = Field(alias="modelWeight", ge=-3, le=10)
    clip_weight: float = Field(alias="clipWeight", ge=-3, le=3)


class ImageGenerationSettingsInput(ApiModel):
    steps: int = Field(default=8, ge=1, le=32)
    cfg: float = Field(default=1.0, ge=0, le=12)
    shift: float = Field(default=5.0, ge=0, le=12)
    sampler: str = Field(default="euler", min_length=1, max_length=80)
    scheduler: str = Field(default="beta", min_length=1, max_length=80)
    loras: list[LoraSelectionInput] = Field(default_factory=list, max_length=8)

    @field_validator("loras")
    @classmethod
    def validate_unique_loras(cls, value: list[LoraSelectionInput]) -> list[LoraSelectionInput]:
        if len({item.id for item in value}) != len(value):
            raise ValueError("Each selected LoRA must be unique.")
        return value


class GPTImageSettingsInput(ApiModel):
    quality: Literal["auto", "low", "medium", "high"] = "auto"
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    count: int = Field(default=1, ge=1, le=2)
    moderation: Literal["auto", "low"] = "auto"
    reasoning_effort: Literal["none", "low", "medium", "high"] = Field(
        default="none", alias="reasoningEffort"
    )
    web_search: bool = Field(default=False, alias="webSearch")


class ImageJobCreate(ApiModel):
    prompt: str = Field(min_length=1, max_length=1200)
    aspect_ratio: AspectRatio = Field(alias="aspectRatio")
    style: ImageStyle
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    generation: ImageGenerationSettingsInput | None = None

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
    generation: ImageGenerationSettingsResponse | None = None
    edit: ImageEditSettingsResponse | None = None
    gpt: GPTImageSettingsResponse | None = None


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


class ImageGenerationSettingsResponse(ApiModel):
    steps: int
    cfg: float
    shift: float
    sampler: str
    scheduler: str
    loras: list[LoraSelectionResponse]


class GPTImageSettingsResponse(ApiModel):
    quality: Literal["auto", "low", "medium", "high"]
    size: str
    count: int = Field(ge=1, le=2)
    moderation: Literal["auto", "low"]
    reasoning_effort: Literal["none", "low", "medium", "high"] = Field(alias="reasoningEffort")
    web_search: bool = Field(alias="webSearch")


class ImageJobResult(ApiModel):
    url: str
    thumbnail_url: str = Field(alias="thumbnailUrl")
    mime_type: ImageMimeType = Field(alias="mimeType")
    width: int
    height: int
    size_bytes: int | None = Field(default=None, alias="sizeBytes", ge=0)
    sha256: str | None = None
    available: bool = True


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
    tags: list[str] = Field(default_factory=list)
    settings: ImageJobSettings
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(alias="startedAt")
    completed_at: datetime | None = Field(alias="completedAt")
    result: ImageJobResult | None
    assets: list[ImageJobResult] = Field(default_factory=list)
    error: ImageJobError | None


class ImageJobListResponse(ApiModel):
    items: list[ImageJobResponse]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class ImageJobTagsUpdate(ApiModel):
    tags: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in value:
            item = " ".join(tag.split()).casefold()
            if not item or len(item) > 48:
                raise ValueError("Tags must contain 1 to 48 visible characters.")
            if item not in normalized:
                normalized.append(item)
        return normalized


class ImageJobTagListResponse(ApiModel):
    tags: list[str]


class ImageJobBatchDelete(ApiModel):
    ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def validate_unique_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Each selected image job must be unique.")
        return value


class ImageJobBatchDeleteResponse(ApiModel):
    deleted_ids: list[str] = Field(alias="deletedIds")


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


class ImageGenerationOptionDefaults(ApiModel):
    steps: int
    cfg: float
    shift: float
    sampler: str
    scheduler: str


class ImageGenerationProviderOptionsResponse(ApiModel):
    samplers: list[str]
    schedulers: list[str]
    loras: list[ImageEditLoraOption]
    defaults: ImageGenerationOptionDefaults


class CodexConnectionResponse(ApiModel):
    state: Literal[
        "disconnected",
        "auth_missing",
        "starting",
        "connected",
        "reauth_required",
        "proxy_error",
    ]
    connected: bool
    message: str
