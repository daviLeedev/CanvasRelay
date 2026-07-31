from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.image_jobs import AspectRatio, ImageJobStatus, ImageStyle


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


class ImageJobResult(ApiModel):
    url: str
    mime_type: Literal["image/svg+xml"] = Field(alias="mimeType")
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
    progress: int = Field(ge=0, le=100)
    prompt: str
    settings: ImageJobSettings
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(alias="startedAt")
    completed_at: datetime | None = Field(alias="completedAt")
    result: ImageJobResult | None
    error: ImageJobError | None
