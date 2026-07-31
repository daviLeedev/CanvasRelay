from __future__ import annotations

from app.domain.image_jobs import (
    AspectRatio,
    ImageGenerationRequest,
    ImageJobRecord,
    ImageProviderName,
    ImageStyle,
    ProviderContent,
    ProviderErrorDetails,
)
from app.providers.base import ImageGenerationProvider, ImageProviderError, ProviderDescriptor
from app.repositories.image_jobs import TERMINAL_STATUSES, ImageJobRepository


class ImageJobService:
    def __init__(
        self,
        repository: ImageJobRepository,
        provider: ImageGenerationProvider,
    ) -> None:
        self.repository = repository
        self.provider = provider

    @property
    def provider_name(self) -> ImageProviderName:
        return self.provider.name

    async def describe_provider(self) -> ProviderDescriptor:
        return await self.provider.describe()

    async def create(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio,
        style: ImageStyle,
        seed: int | None,
    ) -> ImageJobRecord:
        record = self.repository.create(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=seed,
            provider=self.provider.name,
        )
        request = self._request(record)
        try:
            provider_job_id = await self.provider.submit(request)
        except ImageProviderError as error:
            return self.repository.fail_submission(record.id, error.details)
        return self.repository.attach_provider_job(record.id, provider_job_id)

    async def get(self, job_id: str) -> ImageJobRecord:
        record = self.repository.get(job_id)
        if record.status in TERMINAL_STATUSES:
            return record
        if record.provider_job_id is None:
            return record
        snapshot = await self.provider.poll(record.provider_job_id)
        return self.repository.apply_snapshot(job_id, snapshot)

    async def cancel(self, job_id: str) -> ImageJobRecord:
        record = self.repository.get(job_id)
        if record.status in TERMINAL_STATUSES or record.provider_job_id is None:
            return record
        snapshot = await self.provider.cancel(record.provider_job_id)
        return self.repository.apply_snapshot(job_id, snapshot)

    async def collect(self, job_id: str) -> ProviderContent:
        record = await self.get(job_id)
        if record.status != "completed" or record.provider_job_id is None:
            raise ImageProviderError(
                record.error
                or self._result_not_ready_error()
            )
        return await self.provider.collect(record.provider_job_id)

    @staticmethod
    def _request(record: ImageJobRecord) -> ImageGenerationRequest:
        return ImageGenerationRequest(
            job_id=record.id,
            prompt=record.prompt,
            aspect_ratio=record.aspect_ratio,
            style=record.style,
            seed=record.seed,
            created_at=record.created_at,
        )

    @staticmethod
    def _result_not_ready_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "result_not_ready",
            "The image result is not ready.",
            "Wait for the job to complete and try again.",
            True,
        )
