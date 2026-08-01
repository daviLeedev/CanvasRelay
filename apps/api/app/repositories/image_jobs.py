from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from threading import RLock
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import and_, inspect, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.domain.image_jobs import (
    AspectRatio,
    EditFitMode,
    ImageEditSettings,
    ImageJobOperation,
    ImageJobRecord,
    ImageJobStatus,
    ImageMimeType,
    ImageProgressPhase,
    ImageProgressSource,
    ImageProviderName,
    ImageStyle,
    LoraSelection,
    ProviderErrorDetails,
    ProviderResult,
    ProviderSnapshot,
    normalize_prompt,
    resolve_seed,
)
from app.repositories.database import Base, ImageJobRow, create_database_engine

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})


class ImageJobNotFoundError(KeyError):
    pass


class InvalidImageJobCursorError(ValueError):
    pass


class ImageJobRepository:
    """SQLAlchemy repository shared by SQLite tests and PostgreSQL deployments."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        database_path: Path | str = ":memory:",
        *,
        database_url: str | None = None,
        engine: Engine | None = None,
        create_schema: bool = True,
        pool_size: int = 5,
        max_overflow: int = 10,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        resolved_url = database_url or self._sqlite_url(database_path)
        if database_url is None and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = engine or create_database_engine(
            resolved_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)
        if create_schema:
            Base.metadata.create_all(self.engine)
            self._upgrade_legacy_sqlite_table()

    @staticmethod
    def _sqlite_url(database_path: Path | str) -> str:
        if database_path == ":memory:":
            return "sqlite+pysqlite://"
        return f"sqlite+pysqlite:///{Path(database_path).resolve().as_posix()}"

    def _upgrade_legacy_sqlite_table(self) -> None:
        if self.engine.dialect.name != "sqlite":
            return
        columns = {column["name"] for column in inspect(self.engine).get_columns("image_jobs")}
        migrations = {
            "provider_metadata_json": (
                "ALTER TABLE image_jobs ADD COLUMN provider_metadata_json JSON"
            ),
            "thumbnail_path": "ALTER TABLE image_jobs ADD COLUMN thumbnail_path TEXT",
            "result_size_bytes": "ALTER TABLE image_jobs ADD COLUMN result_size_bytes INTEGER",
            "result_sha256": "ALTER TABLE image_jobs ADD COLUMN result_sha256 VARCHAR(64)",
            "result_missing": (
                "ALTER TABLE image_jobs ADD COLUMN result_missing BOOLEAN NOT NULL DEFAULT 0"
            ),
        }
        with self.engine.begin() as connection:
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(text(statement))

    def close(self) -> None:
        self.engine.dispose()

    def now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    def create(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio,
        style: ImageStyle,
        seed: int | None,
        provider: ImageProviderName,
        operation: ImageJobOperation = "generate",
        edit_settings: ImageEditSettings | None = None,
    ) -> ImageJobRecord:
        normalized_prompt = normalize_prompt(prompt)
        record = ImageJobRecord(
            id=f"img_{uuid4().hex}",
            prompt=normalized_prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=resolve_seed(normalized_prompt, aspect_ratio, style, seed),
            provider=provider,
            created_at=self.now(),
            operation=operation,
            edit_settings=edit_settings,
        )
        self.upsert(record)
        return record

    def upsert(self, record: ImageJobRecord) -> ImageJobRecord:
        """Insert or update a complete record, including preserved import identifiers."""
        with self._lock, self._sessions.begin() as session:
            row = session.get(ImageJobRow, record.id)
            if row is None:
                row = ImageJobRow(id=record.id)
                session.add(row)
            self._write_row(row, record)
        return record

    def get(self, job_id: str) -> ImageJobRecord:
        with self._sessions() as session:
            row = session.get(ImageJobRow, job_id)
            if row is None:
                raise ImageJobNotFoundError(job_id)
            return self._from_row(row)

    def exists(self, job_id: str) -> bool:
        with self._sessions() as session:
            return session.get(ImageJobRow, job_id) is not None

    def list_recent(
        self,
        *,
        limit: int = 24,
        status: ImageJobStatus | None = None,
        operation: ImageJobOperation | None = None,
    ) -> list[ImageJobRecord]:
        records, _ = self.list_page(limit=limit, status=status, operation=operation)
        return records

    def list_page(
        self,
        *,
        limit: int = 24,
        status: ImageJobStatus | None = None,
        operation: ImageJobOperation | None = None,
        cursor: str | None = None,
    ) -> tuple[list[ImageJobRecord], str | None]:
        bounded_limit = max(1, min(limit, 100))
        statement = select(ImageJobRow)
        if status is not None:
            statement = statement.where(ImageJobRow.status == status)
        if operation is not None:
            statement = statement.where(ImageJobRow.operation == operation)
        if cursor is not None:
            created_at, job_id = self._decode_cursor(cursor)
            statement = statement.where(
                or_(
                    ImageJobRow.created_at < created_at,
                    and_(ImageJobRow.created_at == created_at, ImageJobRow.id < job_id),
                )
            )
        statement = statement.order_by(ImageJobRow.created_at.desc(), ImageJobRow.id.desc()).limit(
            bounded_limit + 1
        )
        with self._sessions() as session:
            rows = list(session.scalars(statement))
            records = [self._from_row(row) for row in rows[:bounded_limit]]
        next_cursor = (
            self._encode_cursor(records[-1])
            if len(rows) > bounded_limit and records
            else None
        )
        return records, next_cursor

    def has_dependents(self, job_id: str) -> bool:
        with self._sessions() as session:
            statement = select(ImageJobRow.id).where(ImageJobRow.source_job_id == job_id).limit(1)
            return session.scalar(statement) is not None

    def delete(self, job_id: str) -> None:
        with self._lock, self._sessions.begin() as session:
            row = session.get(ImageJobRow, job_id)
            if row is None:
                raise ImageJobNotFoundError(job_id)
            session.delete(row)

    def list_active(self) -> list[ImageJobRecord]:
        statement = (
            select(ImageJobRow)
            .where(ImageJobRow.status.in_(("queued", "running")))
            .order_by(ImageJobRow.created_at.asc())
        )
        with self._sessions() as session:
            return [self._from_row(row) for row in session.scalars(statement)]

    def find_by_provider_job(
        self, provider: ImageProviderName, provider_job_id: str
    ) -> ImageJobRecord | None:
        statement = select(ImageJobRow).where(
            ImageJobRow.provider == provider,
            ImageJobRow.provider_job_id == provider_job_id,
        )
        with self._sessions() as session:
            row = session.scalar(statement)
            return self._from_row(row) if row is not None else None

    def attach_provider_job(self, job_id: str, provider_job_id: str) -> ImageJobRecord:
        with self._lock:
            record = replace(self.get(job_id), provider_job_id=provider_job_id)
            return self.upsert(record)

    def attach_inputs(
        self,
        job_id: str,
        *,
        source_path: str,
        source_job_id: str | None = None,
        face_reference_path: str | None = None,
    ) -> ImageJobRecord:
        with self._lock:
            record = replace(
                self.get(job_id),
                source_path=source_path,
                source_job_id=source_job_id,
                face_reference_path=face_reference_path,
            )
            return self.upsert(record)

    def apply_snapshot(
        self,
        job_id: str,
        snapshot: ProviderSnapshot,
        *,
        result_path: str | None = None,
        thumbnail_path: str | None = None,
        result_size_bytes: int | None = None,
        result_sha256: str | None = None,
    ) -> ImageJobRecord:
        with self._lock, self._sessions.begin() as session:
            row = session.scalar(
                select(ImageJobRow)
                .where(ImageJobRow.id == job_id)
                .with_for_update()
            )
            if row is None:
                raise ImageJobNotFoundError(job_id)
            record = self._from_row(row)
            if record.status in TERMINAL_STATUSES:
                return record
            now = self.now()
            started_at = record.started_at
            if snapshot.status == "running" and started_at is None:
                started_at = now
            completed_at = record.completed_at
            if snapshot.status in TERMINAL_STATUSES and completed_at is None:
                completed_at = now
            phase = snapshot.phase
            if phase == "queued" and snapshot.status != "queued":
                phase = "preparing" if snapshot.status == "running" else snapshot.status
            updated = replace(
                record,
                status=snapshot.status,
                progress=snapshot.progress,
                phase=phase,
                current_step=(
                    snapshot.current_step
                    if snapshot.current_step is not None or snapshot.status != "running"
                    else record.current_step
                ),
                total_steps=(
                    snapshot.total_steps
                    if snapshot.total_steps is not None or snapshot.status != "running"
                    else record.total_steps
                ),
                progress_source=snapshot.progress_source,
                progress_updated_at=snapshot.progress_updated_at or record.progress_updated_at,
                stalled=snapshot.stalled,
                started_at=started_at,
                completed_at=completed_at,
                result=snapshot.result,
                result_path=result_path or record.result_path,
                thumbnail_path=thumbnail_path or record.thumbnail_path,
                result_size_bytes=(
                    result_size_bytes if result_size_bytes is not None else record.result_size_bytes
                ),
                result_sha256=result_sha256 or record.result_sha256,
                result_missing=False if result_path else record.result_missing,
                error=snapshot.error,
            )
            self._write_row(row, updated)
            return updated

    def update_storage_metadata(
        self,
        job_id: str,
        *,
        thumbnail_path: str | None,
        result_size_bytes: int | None,
        result_sha256: str | None,
        result_missing: bool,
    ) -> ImageJobRecord:
        with self._lock:
            record = replace(
                self.get(job_id),
                thumbnail_path=thumbnail_path,
                result_size_bytes=result_size_bytes,
                result_sha256=result_sha256,
                result_missing=result_missing,
            )
            return self.upsert(record)

    def mark_stalled(self, job_id: str) -> ImageJobRecord:
        record = self.get(job_id)
        if record.status in TERMINAL_STATUSES:
            return record
        with self._lock:
            return self.upsert(replace(self.get(job_id), stalled=True))

    def fail_submission(self, job_id: str, error: ProviderErrorDetails) -> ImageJobRecord:
        return self.apply_snapshot(
            job_id,
            ProviderSnapshot("failed", None, error=error, phase="failed"),
        )

    def median_duration_seconds(self, record: ImageJobRecord, limit: int = 10) -> float | None:
        statement = (
            select(ImageJobRow.started_at, ImageJobRow.completed_at)
            .where(
                ImageJobRow.status == "completed",
                ImageJobRow.operation == record.operation,
                ImageJobRow.aspect_ratio == record.aspect_ratio,
                ImageJobRow.started_at.is_not(None),
                ImageJobRow.completed_at.is_not(None),
                ImageJobRow.id != record.id,
                ImageJobRow.face_reference_path.is_not(None)
                if record.face_reference_path
                else ImageJobRow.face_reference_path.is_(None),
            )
            .order_by(ImageJobRow.completed_at.desc())
            .limit(max(1, min(limit, 30)))
        )
        with self._sessions() as session:
            rows = session.execute(statement).all()
        durations = [
            (self._aware(completed) - self._aware(started)).total_seconds()
            for started, completed in rows
            if started is not None and completed is not None
        ]
        return float(median(durations)) if durations else None

    @staticmethod
    def _encode_cursor(record: ImageJobRecord) -> str:
        raw = f"{record.created_at.isoformat()}|{record.id}".encode()
        return urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, str]:
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = urlsafe_b64decode(f"{cursor}{padding}").decode()
            created_at_raw, job_id = raw.rsplit("|", 1)
            created_at = datetime.fromisoformat(created_at_raw)
        except (Base64Error, UnicodeDecodeError, ValueError) as error:
            raise InvalidImageJobCursorError("Invalid image job cursor.") from error
        if not job_id.startswith("img_"):
            raise InvalidImageJobCursorError("Invalid image job cursor.")
        return ImageJobRepository._aware(created_at), job_id

    def _write_row(self, row: ImageJobRow, record: ImageJobRecord) -> None:
        result = record.result
        error = record.error
        row.prompt = record.prompt
        row.aspect_ratio = record.aspect_ratio
        row.style = record.style
        row.seed = record.seed
        row.provider = record.provider
        row.operation = record.operation
        row.source_path = record.source_path
        row.source_job_id = record.source_job_id
        row.face_reference_path = record.face_reference_path
        row.edit_settings_json = self._serialize_edit_settings(record.edit_settings)
        row.provider_metadata_json = record.provider_metadata
        row.created_at = record.created_at
        row.provider_job_id = record.provider_job_id
        row.status = record.status
        row.progress = record.progress
        row.phase = record.phase
        row.current_step = record.current_step
        row.total_steps = record.total_steps
        row.progress_source = record.progress_source
        row.progress_updated_at = record.progress_updated_at
        row.stalled = record.stalled
        row.started_at = record.started_at
        row.completed_at = record.completed_at
        row.result_mime_type = result.mime_type if result else None
        row.result_width = result.width if result else None
        row.result_height = result.height if result else None
        row.result_path = record.result_path
        row.thumbnail_path = record.thumbnail_path
        row.result_size_bytes = record.result_size_bytes
        row.result_sha256 = record.result_sha256
        row.result_missing = record.result_missing
        row.error_code = error.code if error else None
        row.error_message = error.message if error else None
        row.error_action = error.action if error else None
        row.error_retryable = error.retryable if error else None
        row.updated_at = self.now()

    @staticmethod
    def _from_row(row: ImageJobRow) -> ImageJobRecord:
        result = None
        if row.result_mime_type is not None:
            result = ProviderResult(
                cast(ImageMimeType, row.result_mime_type),
                cast(int, row.result_width),
                cast(int, row.result_height),
            )
        error = None
        if row.error_code is not None:
            error = ProviderErrorDetails(
                row.error_code,
                row.error_message or "The image job failed.",
                row.error_action or "Retry the job.",
                bool(row.error_retryable),
            )
        return ImageJobRecord(
            id=row.id,
            prompt=row.prompt,
            aspect_ratio=cast(AspectRatio, row.aspect_ratio),
            style=cast(ImageStyle, row.style),
            seed=row.seed,
            provider=cast(ImageProviderName, row.provider),
            created_at=ImageJobRepository._aware(row.created_at),
            operation=cast(ImageJobOperation, row.operation),
            source_path=row.source_path,
            source_job_id=row.source_job_id,
            face_reference_path=row.face_reference_path,
            edit_settings=ImageJobRepository._parse_edit_settings(row.edit_settings_json),
            provider_job_id=row.provider_job_id,
            status=cast(ImageJobStatus, row.status),
            progress=row.progress,
            phase=cast(ImageProgressPhase, row.phase),
            current_step=row.current_step,
            total_steps=row.total_steps,
            progress_source=cast(ImageProgressSource, row.progress_source),
            progress_updated_at=(
                ImageJobRepository._aware(row.progress_updated_at)
                if row.progress_updated_at is not None
                else None
            ),
            stalled=row.stalled,
            started_at=(
                ImageJobRepository._aware(row.started_at) if row.started_at is not None else None
            ),
            completed_at=(
                ImageJobRepository._aware(row.completed_at)
                if row.completed_at is not None
                else None
            ),
            result=result,
            result_path=row.result_path,
            thumbnail_path=row.thumbnail_path,
            result_size_bytes=row.result_size_bytes,
            result_sha256=row.result_sha256,
            result_missing=row.result_missing,
            provider_metadata=cast(dict[str, object] | None, row.provider_metadata_json),
            error=error,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _serialize_edit_settings(settings: ImageEditSettings | None) -> dict[str, object] | None:
        if settings is None:
            return None
        return {
            "steps": settings.steps,
            "cfg": settings.cfg,
            "referenceInfluence": settings.reference_influence,
            "groundingResolution": settings.grounding_resolution,
            "fitMode": settings.fit_mode,
            "sampler": settings.sampler,
            "scheduler": settings.scheduler,
            "loras": [
                {
                    "id": item.id,
                    "modelWeight": item.model_weight,
                    "clipWeight": item.clip_weight,
                }
                for item in settings.loras
            ],
        }

    @staticmethod
    def _parse_edit_settings(value: object) -> ImageEditSettings | None:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return None
        if not isinstance(value, dict):
            return None
        payload = cast(dict[str, Any], value)
        raw_loras = payload.get("loras", [])
        return ImageEditSettings(
            steps=int(payload.get("steps", 8)),
            cfg=float(payload.get("cfg", 1.0)),
            reference_influence=float(payload.get("referenceInfluence", 4.0)),
            grounding_resolution=int(payload.get("groundingResolution", 768)),
            fit_mode=cast(EditFitMode, payload.get("fitMode", "fit")),
            sampler=str(payload.get("sampler", "euler")),
            scheduler=str(payload.get("scheduler", "simple")),
            loras=tuple(
                LoraSelection(
                    id=str(item["id"]),
                    model_weight=float(item.get("modelWeight", 1.0)),
                    clip_weight=float(item.get("clipWeight", 1.0)),
                )
                for item in raw_loras
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ),
        )
