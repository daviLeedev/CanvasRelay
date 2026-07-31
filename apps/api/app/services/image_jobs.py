from __future__ import annotations

from app.domain.image_jobs import (
    AspectRatio,
    ImageGenerationRequest,
    ImageJobRecord,
    ImageJobStatus,
    ImageProviderName,
    ImageStyle,
    ProviderContent,
    ProviderErrorDetails,
    ProviderSnapshot,
)
from app.providers.base import ImageGenerationProvider, ImageProviderError, ProviderDescriptor
from app.repositories.image_jobs import TERMINAL_STATUSES, ImageJobRepository
from app.repositories.media import FilesystemMediaStore, MediaNotFoundError


class ImageJobService:
    def __init__(
        self,
        repository: ImageJobRepository,
        provider: ImageGenerationProvider,
        media_store: FilesystemMediaStore,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.media_store = media_store
        self._resume_active_jobs()

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

    async def list_recent(
        self,
        *,
        limit: int = 24,
        status: ImageJobStatus | None = None,
    ) -> list[ImageJobRecord]:
        if status is not None:
            for active_record in self.repository.list_active():
                await self.get(active_record.id)
        records = self.repository.list_recent(limit=limit, status=status)
        refreshed: list[ImageJobRecord] = []
        for record in records:
            if record.status in TERMINAL_STATUSES:
                refreshed.append(record)
            else:
                refreshed.append(await self.get(record.id))
        return refreshed

    async def get(self, job_id: str) -> ImageJobRecord:
        record = self.repository.get(job_id)
        if record.status in TERMINAL_STATUSES:
            return record
        if record.provider_job_id is None:
            return record
        if record.provider != self.provider.name:
            return self.repository.apply_snapshot(
                record.id,
                ProviderSnapshot("failed", None, error=self._provider_mismatch_error()),
            )
        snapshot = await self.provider.poll(record.provider_job_id)
        if snapshot.status == "completed":
            return await self._persist_completed(record, snapshot)
        return self.repository.apply_snapshot(job_id, snapshot)

    async def cancel(self, job_id: str) -> ImageJobRecord:
        record = self.repository.get(job_id)
        if record.status in TERMINAL_STATUSES or record.provider_job_id is None:
            return record
        snapshot = await self.provider.cancel(record.provider_job_id)
        return self.repository.apply_snapshot(job_id, snapshot)

    async def collect(self, job_id: str) -> ProviderContent:
        record = await self.get(job_id)
        if record.status != "completed" or record.result is None or record.result_path is None:
            raise ImageProviderError(record.error or self._result_not_ready_error())
        try:
            return self.media_store.read(record.result_path, record.result.mime_type)
        except MediaNotFoundError as error:
            raise ImageProviderError(self._stored_result_missing_error()) from error

    async def _persist_completed(
        self,
        record: ImageJobRecord,
        snapshot: ProviderSnapshot,
    ) -> ImageJobRecord:
        if record.provider_job_id is None or snapshot.result is None:
            return self.repository.apply_snapshot(
                record.id,
                ProviderSnapshot("failed", None, error=self._result_not_ready_error()),
            )
        try:
            content = await self.provider.collect(record.provider_job_id)
            result_path = self.media_store.save(record.id, content)
        except (ImageProviderError, OSError, ValueError) as error:
            details = (
                error.details
                if isinstance(error, ImageProviderError)
                else self._media_persist_error()
            )
            return self.repository.apply_snapshot(
                record.id,
                ProviderSnapshot("failed", None, error=details),
            )
        return self.repository.apply_snapshot(
            record.id,
            snapshot,
            result_path=result_path,
        )

    def _resume_active_jobs(self) -> None:
        for record in self.repository.list_active():
            if record.provider != self.provider.name or record.provider_job_id is None:
                continue
            self.provider.resume(record.provider_job_id, self._request(record))

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

    @staticmethod
    def _media_persist_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "media_persist_failed",
            "CanvasRelay could not store the completed image.",
            "Check the configured data directory and retry generation.",
            True,
        )

    @staticmethod
    def _stored_result_missing_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "stored_result_missing",
            "The stored image file is no longer available.",
            "Check the CanvasRelay data directory or create a new image.",
            False,
        )

    @staticmethod
    def _provider_mismatch_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "provider_mismatch",
            "This saved job belongs to a different image provider.",
            "Switch back to the original provider or create a new image job.",
            False,
        )
