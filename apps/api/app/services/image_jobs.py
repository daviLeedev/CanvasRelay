from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.domain.image_jobs import (
    AspectRatio,
    ImageEditSettings,
    ImageGenerationRequest,
    ImageGenerationSettings,
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
    ImageGenerationProviderOptions,
    ImageProviderError,
    ProviderDescriptor,
)
from app.repositories.image_jobs import TERMINAL_STATUSES, ImageJobRepository
from app.repositories.media import (
    FilesystemMediaStore,
    FilesystemUploadStore,
    MediaNotFoundError,
    StagedFileDeletion,
    StoredMediaFile,
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

    async def describe_generation_options(self) -> ImageGenerationProviderOptions:
        return await self.provider.describe_generation_options()

    async def create(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio,
        style: ImageStyle,
        seed: int | None,
        generation_settings: ImageGenerationSettings,
    ) -> ImageJobRecord:
        record = self.repository.create(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=seed,
            provider=self.provider.name,
            generation_settings=generation_settings,
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
        return await self._create_edit_with_content(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=seed,
            source=source,
            source_job_id=source_job_id,
            face_reference=face_reference,
            edit_settings=edit_settings,
        )

    async def _create_edit_with_content(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio,
        style: ImageStyle,
        seed: int | None,
        source: ProviderContent,
        source_job_id: str | None,
        face_reference: ProviderContent | None,
        edit_settings: ImageEditSettings,
    ) -> ImageJobRecord:
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
                try:
                    await self.get(active_record.id)
                except ImageProviderError:
                    self.repository.mark_stalled(active_record.id)
        records = self.repository.list_recent(limit=limit, status=status, operation=operation)
        refreshed: list[ImageJobRecord] = []
        for record in records:
            if record.status in TERMINAL_STATUSES:
                refreshed.append(record)
            else:
                try:
                    refreshed.append(await self.get(record.id))
                except ImageProviderError:
                    refreshed.append(self.repository.mark_stalled(record.id))
        return refreshed

    async def list_page(
        self,
        *,
        limit: int = 24,
        status: ImageJobStatus | None = None,
        operation: ImageJobOperation | None = None,
        cursor: str | None = None,
    ) -> tuple[list[ImageJobRecord], str | None]:
        if cursor is None:
            records = await self.list_recent(limit=limit, status=status, operation=operation)
            _, next_cursor = self.repository.list_page(
                limit=limit,
                status=status,
                operation=operation,
            )
            return records, next_cursor

        records, next_cursor = self.repository.list_page(
            limit=limit,
            status=status,
            operation=operation,
            cursor=cursor,
        )
        refreshed: list[ImageJobRecord] = []
        for record in records:
            if record.status in TERMINAL_STATUSES:
                refreshed.append(record)
            else:
                try:
                    refreshed.append(await self.get(record.id))
                except ImageProviderError:
                    refreshed.append(self.repository.mark_stalled(record.id))
        return refreshed, next_cursor

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
        # Provider clients keep short-lived connection state in memory. Rehydrate
        # it from the durable record before every reconciliation attempt.
        self.provider.resume(record.provider_job_id, self._request(record))
        try:
            snapshot = await self.provider.poll(record.provider_job_id)
        except ImageProviderError as error:
            if error.details.code == "provider_unavailable":
                return self._with_estimate(self.repository.mark_stalled(record.id))
            if error.details.code == "provider_restarted":
                return self._with_estimate(
                    self.repository.apply_snapshot(
                        record.id,
                        ProviderSnapshot("failed", None, error=error.details, phase="failed"),
                    )
                )
            raise
        if snapshot.status == "completed":
            return await self._persist_completed(record, snapshot)
        return self._with_estimate(self.repository.apply_snapshot(job_id, snapshot))

    async def retry(self, job_id: str) -> ImageJobRecord:
        record = self.repository.get(job_id)
        if record.status != "failed" or record.error is None or not record.error.retryable:
            raise ImageProviderError(self._retry_not_available_error())

        if record.operation == "generate":
            return await self.create(
                prompt=record.prompt,
                aspect_ratio=record.aspect_ratio,
                style=record.style,
                seed=record.seed,
                generation_settings=record.generation_settings or ImageGenerationSettings(),
            )

        if record.edit_settings is None or record.source_path is None:
            raise ImageProviderError(self._retry_not_available_error())
        try:
            source = self.upload_store.read(
                record.source_path,
                self._mime_for_path(record.source_path),
            )
            face_reference = (
                self.upload_store.read(
                    record.face_reference_path,
                    self._mime_for_path(record.face_reference_path),
                )
                if record.face_reference_path is not None
                else None
            )
        except (MediaNotFoundError, ValueError) as error:
            raise ImageProviderError(self._stored_input_missing_error()) from error

        return await self._create_edit_with_content(
            prompt=record.prompt,
            aspect_ratio=record.aspect_ratio,
            style=record.style,
            seed=record.seed,
            source=source,
            source_job_id=record.source_job_id,
            face_reference=face_reference,
            edit_settings=record.edit_settings,
        )

    async def cancel(self, job_id: str) -> ImageJobRecord:
        record = self.repository.get(job_id)
        if record.status in TERMINAL_STATUSES or record.provider_job_id is None:
            return record
        snapshot = await self.provider.cancel(record.provider_job_id)
        return self.repository.apply_snapshot(job_id, snapshot)

    def delete_asset(self, job_id: str) -> None:
        record = self.repository.get(job_id)
        if record.status != "completed" or record.result_path is None:
            raise ImageProviderError(self._asset_not_deletable_error())
        if self.repository.has_dependents(job_id):
            raise ImageProviderError(self._asset_in_use_error())

        staged: list[StagedFileDeletion | None] = []
        try:
            staged.append(self.media_store.stage_delete(record.result_path))
            staged.append(self.media_store.stage_thumbnail_delete(record.thumbnail_path))
            if record.source_path is not None:
                staged.append(self.upload_store.stage_delete(record.source_path))
            if record.face_reference_path is not None:
                staged.append(self.upload_store.stage_delete(record.face_reference_path))
            self.repository.delete(job_id)
        except Exception as error:
            for item in reversed(staged):
                FilesystemMediaStore.restore_delete(item)
            raise ImageProviderError(self._asset_delete_failed_error()) from error
        for item in staged:
            FilesystemMediaStore.finalize_delete(item)

    async def collect(self, job_id: str) -> ProviderContent:
        record = await self.get(job_id)
        if record.status != "completed" or record.result is None or record.result_path is None:
            raise ImageProviderError(record.error or self._result_not_ready_error())
        try:
            return self.media_store.read(record.result_path, record.result.mime_type)
        except MediaNotFoundError as error:
            raise ImageProviderError(self._stored_result_missing_error()) from error

    async def resolve_result_file(
        self, job_id: str, *, thumbnail: bool = False
    ) -> StoredMediaFile:
        record = await self.get(job_id)
        if record.status != "completed" or record.result is None or record.result_path is None:
            raise ImageProviderError(record.error or self._result_not_ready_error())
        try:
            if thumbnail and record.thumbnail_path is not None:
                return self.media_store.describe_thumbnail(record.thumbnail_path)
            return self.media_store.describe(record.result_path, record.result.mime_type)
        except (MediaNotFoundError, ValueError) as error:
            if not record.result_missing:
                self.repository.update_storage_metadata(
                    record.id,
                    thumbnail_path=record.thumbnail_path,
                    result_size_bytes=record.result_size_bytes,
                    result_sha256=record.result_sha256,
                    result_missing=True,
                )
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

    def resolve_input_file(self, job_id: str, role: str) -> StoredMediaFile:
        record = self.repository.get(job_id)
        path = record.source_path if role == "source" else record.face_reference_path
        if role not in {"source", "identity"} or path is None:
            raise ImageProviderError(self._stored_input_missing_error())
        try:
            return self.upload_store.describe(path, self._mime_for_path(path))
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
            stored = self.media_store.save_with_metadata(record.id, content)
            thumbnail_path = self.media_store.ensure_thumbnail(
                stored.storage_key,
                content.mime_type,
            )
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
            self.repository.apply_snapshot(
                record.id,
                snapshot,
                result_path=stored.storage_key,
                thumbnail_path=thumbnail_path,
                result_size_bytes=stored.size_bytes,
                result_sha256=stored.sha256,
            )
        )

    def _resume_active_jobs(self) -> None:
        for record in self.repository.list_active():
            if record.provider_job_id is None:
                self.repository.fail_submission(record.id, self._submission_interrupted_error())
                continue
            if record.provider != self.provider.name:
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
            generation_settings=record.generation_settings,
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

    @staticmethod
    def _retry_not_available_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "retry_not_available",
            "This saved job cannot be retried.",
            "Choose a retryable failed job or create a new image job.",
            False,
        )

    @staticmethod
    def _submission_interrupted_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "submission_interrupted",
            "The provider restart interrupted this job before it was submitted.",
            "Your settings were preserved. Retry the job when the provider is ready.",
            True,
        )

    @staticmethod
    def _asset_not_deletable_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "asset_not_deletable",
            "Only completed Library results can be deleted.",
            "Wait for the job to finish or cancel it from Job Center.",
            False,
        )

    @staticmethod
    def _asset_in_use_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "asset_in_use",
            "This image is used as the source of another saved edit.",
            "Delete the dependent edit first, or keep this source image.",
            False,
        )

    @staticmethod
    def _asset_delete_failed_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "asset_delete_failed",
            "CanvasRelay could not delete the stored image.",
            "Check the data directory permissions and try again.",
            True,
        )
