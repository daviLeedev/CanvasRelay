from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.domain.image_jobs import (
    AspectRatio,
    ImageEditSettings,
    ImageGenerationRequest,
    ImageJobOperation,
    ImageJobRecord,
    ImageJobStatus,
    ImageMimeType,
    ImageProviderName,
    ImageStyle,
    ProviderContent,
    ProviderErrorDetails,
    ProviderSnapshot,
)
from app.providers.base import (
    ImageEditProviderOptions,
    ImageGenerationProvider,
    ImageProviderError,
    ProviderDescriptor,
)
from app.repositories.image_jobs import TERMINAL_STATUSES, ImageJobRepository
from app.repositories.media import (
    FilesystemMediaStore,
    FilesystemUploadStore,
    MediaNotFoundError,
)


class ImageJobService:
    def __init__(
        self,
        repository: ImageJobRepository,
        provider: ImageGenerationProvider,
        media_store: FilesystemMediaStore,
        upload_store: FilesystemUploadStore,
        max_upload_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.media_store = media_store
        self.upload_store = upload_store
        self.max_upload_bytes = max_upload_bytes
        self._resume_active_jobs()

    @property
    def provider_name(self) -> ImageProviderName:
        return self.provider.name

    async def describe_provider(self) -> ProviderDescriptor:
        return await self.provider.describe()

    async def describe_edit_provider(self) -> ProviderDescriptor:
        return await self.provider.describe_edit()

    async def describe_edit_options(self) -> ImageEditProviderOptions:
        return await self.provider.describe_edit_options()

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

    async def create_edit(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio,
        style: ImageStyle,
        seed: int | None,
        source: ProviderContent | None,
        source_job_id: str | None,
        face_reference: ProviderContent | None,
        edit_settings: ImageEditSettings,
    ) -> ImageJobRecord:
        if (source is None) == (source_job_id is None):
            raise ImageProviderError(self._source_choice_error())
        if source_job_id is not None:
            source = await self._resolve_source_job(source_job_id)
        if source is None:
            raise ImageProviderError(self._source_choice_error())
        record = self.repository.create(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=seed,
            provider=self.provider.name,
            operation="edit",
            edit_settings=edit_settings,
        )
        try:
            source_path = self.upload_store.save(record.id, "source", source)
            face_path = (
                self.upload_store.save(record.id, "face", face_reference)
                if face_reference is not None
                else None
            )
            record = self.repository.attach_inputs(
                record.id,
                source_path=source_path,
                source_job_id=source_job_id,
                face_reference_path=face_path,
            )
            provider_job_id = await self.provider.submit_edit(
                self._request(record),
                source,
                face_reference,
            )
        except ImageProviderError as error:
            return self.repository.fail_submission(record.id, error.details)
        except (OSError, ValueError):
            return self.repository.fail_submission(record.id, self._upload_persist_error())
        return self.repository.attach_provider_job(record.id, provider_job_id)

    async def list_recent(
        self,
        *,
        limit: int = 24,
        status: ImageJobStatus | None = None,
        operation: ImageJobOperation | None = None,
    ) -> list[ImageJobRecord]:
        if status is not None:
            for active_record in self.repository.list_active():
                await self.get(active_record.id)
        records = self.repository.list_recent(limit=limit, status=status, operation=operation)
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
            return self._with_estimate(record)
        if record.provider_job_id is None:
            return self._with_estimate(record)
        if record.provider != self.provider.name:
            return self._with_estimate(
                self.repository.apply_snapshot(
                    record.id,
                    ProviderSnapshot(
                        "failed",
                        None,
                        error=self._provider_mismatch_error(),
                        phase="failed",
                    ),
                )
            )
        snapshot = await self.provider.poll(record.provider_job_id)
        if snapshot.status == "completed":
            return await self._persist_completed(record, snapshot)
        return self._with_estimate(self.repository.apply_snapshot(job_id, snapshot))

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

    async def collect_input(self, job_id: str, role: str) -> ProviderContent:
        record = self.repository.get(job_id)
        path = record.source_path if role == "source" else record.face_reference_path
        if role not in {"source", "identity"} or path is None:
            raise ImageProviderError(self._stored_input_missing_error())
        try:
            return self.upload_store.read(path, self._mime_for_path(path))
        except (MediaNotFoundError, ValueError) as error:
            raise ImageProviderError(self._stored_input_missing_error()) from error

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
        self.repository.apply_snapshot(
            record.id,
            ProviderSnapshot(
                "running",
                snapshot.progress,
                phase="saving",
                current_step=snapshot.current_step,
                total_steps=snapshot.total_steps,
                progress_source=snapshot.progress_source,
                progress_updated_at=snapshot.progress_updated_at,
            ),
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
        return self._with_estimate(
            self.repository.apply_snapshot(record.id, snapshot, result_path=result_path)
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
            edit_settings=record.edit_settings,
        )

    async def _resolve_source_job(self, job_id: str) -> ProviderContent:
        try:
            record = self.repository.get(job_id)
        except KeyError as error:
            raise ImageProviderError(self._source_job_invalid_error()) from error
        if record.status != "completed" or record.result is None or record.result_path is None:
            raise ImageProviderError(self._source_job_invalid_error())
        try:
            return self.media_store.read(record.result_path, record.result.mime_type)
        except (MediaNotFoundError, ValueError) as error:
            raise ImageProviderError(self._source_job_invalid_error()) from error

    def _with_estimate(self, record: ImageJobRecord) -> ImageJobRecord:
        if record.status not in {"queued", "running"} or record.started_at is None:
            return record
        typical = self.repository.median_duration_seconds(record)
        if typical is None:
            return record
        elapsed = max(0.0, (datetime.now(UTC) - record.started_at).total_seconds())
        return replace(record, estimated_remaining_seconds=max(0, round(typical - elapsed)))

    @staticmethod
    def _mime_for_path(path: str) -> ImageMimeType:
        suffix = Path(path).suffix.lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }.get(suffix)
        if mime_type is None:
            raise ValueError("Unsupported stored image type.")
        return cast(ImageMimeType, mime_type)

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

    @staticmethod
    def _upload_persist_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "upload_persist_failed",
            "CanvasRelay could not store the selected image.",
            "Check the configured data directory and choose the image again.",
            True,
        )

    @staticmethod
    def _source_choice_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "edit_source_invalid",
            "Choose one source image for this edit.",
            "Upload an image or select one completed Library result.",
            False,
        )

    @staticmethod
    def _source_job_invalid_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "library_source_invalid",
            "The selected Library image is not available for editing.",
            "Choose another completed image result.",
            False,
        )

    @staticmethod
    def _stored_input_missing_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "stored_input_missing",
            "The saved edit input is no longer available.",
            "Choose the source image again.",
            False,
        )
