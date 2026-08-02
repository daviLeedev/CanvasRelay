from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.image_jobs import (
    ImageGenerationRequest,
    ImageProviderName,
    ProviderContent,
    ProviderErrorDetails,
    ProviderSnapshot,
)


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider: ImageProviderName
    label: str
    ready: bool
    message: str


@dataclass(frozen=True, slots=True)
class LoraOption:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class ImageEditProviderOptions:
    samplers: tuple[str, ...]
    schedulers: tuple[str, ...]
    loras: tuple[LoraOption, ...]
    default_sampler: str = "euler"
    default_scheduler: str = "simple"
    default_steps: int = 8
    default_cfg: float = 1.0


@dataclass(frozen=True, slots=True)
class ImageGenerationProviderOptions:
    samplers: tuple[str, ...]
    schedulers: tuple[str, ...]
    loras: tuple[LoraOption, ...]
    default_sampler: str = "euler"
    default_scheduler: str = "beta"
    default_steps: int = 8
    default_cfg: float = 1.0
    default_shift: float = 5.0


class ImageProviderError(RuntimeError):
    def __init__(self, details: ProviderErrorDetails) -> None:
        super().__init__(details.message)
        self.details = details


class ImageGenerationProvider(Protocol):
    name: ImageProviderName

    async def describe(self) -> ProviderDescriptor: ...

    async def describe_edit(self) -> ProviderDescriptor: ...

    async def describe_edit_options(self) -> ImageEditProviderOptions: ...

    async def describe_generation_options(self) -> ImageGenerationProviderOptions: ...

    async def submit(self, request: ImageGenerationRequest) -> str: ...

    async def submit_edit(
        self,
        request: ImageGenerationRequest,
        source: ProviderContent,
        face_reference: ProviderContent | None,
    ) -> str: ...

    def resume(self, provider_job_id: str, request: ImageGenerationRequest) -> None: ...

    async def poll(self, provider_job_id: str) -> ProviderSnapshot: ...

    async def cancel(self, provider_job_id: str) -> ProviderSnapshot: ...

    async def collect(self, provider_job_id: str) -> ProviderContent: ...
