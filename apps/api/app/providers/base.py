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


class ImageProviderError(RuntimeError):
    def __init__(self, details: ProviderErrorDetails) -> None:
        super().__init__(details.message)
        self.details = details


class ImageGenerationProvider(Protocol):
    name: ImageProviderName

    async def describe(self) -> ProviderDescriptor: ...

    async def describe_edit(self) -> ProviderDescriptor: ...

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
