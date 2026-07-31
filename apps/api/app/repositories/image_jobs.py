from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from threading import RLock
from typing import cast
from uuid import uuid4

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

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})


class ImageJobNotFoundError(KeyError):
    pass


class ImageJobRepository:
    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        database_path: Path | str = ":memory:",
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = RLock()
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(database_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            if database_path != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS image_jobs (
                    id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    aspect_ratio TEXT NOT NULL,
                    style TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    operation TEXT NOT NULL DEFAULT 'generate',
                    source_path TEXT,
                    source_job_id TEXT,
                    face_reference_path TEXT,
                    edit_settings_json TEXT,
                    created_at TEXT NOT NULL,
                    provider_job_id TEXT,
                    status TEXT NOT NULL,
                    progress INTEGER,
                    phase TEXT NOT NULL DEFAULT 'queued',
                    current_step INTEGER,
                    total_steps INTEGER,
                    progress_source TEXT NOT NULL DEFAULT 'unknown',
                    progress_updated_at TEXT,
                    stalled INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT,
                    completed_at TEXT,
                    result_mime_type TEXT,
                    result_width INTEGER,
                    result_height INTEGER,
                    result_path TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    error_action TEXT,
                    error_retryable INTEGER,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                cast(str, row["name"])
                for row in self._connection.execute("PRAGMA table_info(image_jobs)").fetchall()
            }
            migrations = {
                "operation": (
                    "ALTER TABLE image_jobs ADD COLUMN operation "
                    "TEXT NOT NULL DEFAULT 'generate'"
                ),
                "source_path": "ALTER TABLE image_jobs ADD COLUMN source_path TEXT",
                "source_job_id": "ALTER TABLE image_jobs ADD COLUMN source_job_id TEXT",
                "face_reference_path": "ALTER TABLE image_jobs ADD COLUMN face_reference_path TEXT",
                "edit_settings_json": "ALTER TABLE image_jobs ADD COLUMN edit_settings_json TEXT",
                "phase": "ALTER TABLE image_jobs ADD COLUMN phase TEXT NOT NULL DEFAULT 'queued'",
                "current_step": "ALTER TABLE image_jobs ADD COLUMN current_step INTEGER",
                "total_steps": "ALTER TABLE image_jobs ADD COLUMN total_steps INTEGER",
                "progress_source": (
                    "ALTER TABLE image_jobs ADD COLUMN progress_source "
                    "TEXT NOT NULL DEFAULT 'unknown'"
                ),
                "progress_updated_at": (
                    "ALTER TABLE image_jobs ADD COLUMN progress_updated_at TEXT"
                ),
                "stalled": "ALTER TABLE image_jobs ADD COLUMN stalled INTEGER NOT NULL DEFAULT 0",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    self._connection.execute(statement)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS image_jobs_created_idx "
                "ON image_jobs(created_at DESC)"
            )
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def now(self) -> datetime:
        return self._clock()

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
        with self._lock:
            self._write(record)
        return record

    def get(self, job_id: str) -> ImageJobRecord:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM image_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise ImageJobNotFoundError(job_id)
        return self._from_row(row)

    def list_recent(
        self,
        *,
        limit: int = 24,
        status: ImageJobStatus | None = None,
        operation: ImageJobOperation | None = None,
    ) -> list[ImageJobRecord]:
        bounded_limit = max(1, min(limit, 100))
        query = "SELECT * FROM image_jobs"
        filters: list[str] = []
        values: list[object] = []
        if status is not None:
            filters.append("status = ?")
            values.append(status)
        if operation is not None:
            filters.append("operation = ?")
            values.append(operation)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY created_at DESC LIMIT ?"
        values.append(bounded_limit)
        with self._lock:
            rows = self._connection.execute(query, tuple(values)).fetchall()
        return [self._from_row(row) for row in rows]

    def list_active(self) -> list[ImageJobRecord]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM image_jobs WHERE status IN ('queued', 'running') "
                "ORDER BY created_at ASC"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def attach_provider_job(self, job_id: str, provider_job_id: str) -> ImageJobRecord:
        with self._lock:
            record = self._required(job_id)
            record = replace(record, provider_job_id=provider_job_id)
            self._write(record)
        return record

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
                self._required(job_id),
                source_path=source_path,
                source_job_id=source_job_id,
                face_reference_path=face_reference_path,
            )
            self._write(record)
        return record

    def apply_snapshot(
        self,
        job_id: str,
        snapshot: ProviderSnapshot,
        *,
        result_path: str | None = None,
    ) -> ImageJobRecord:
        with self._lock:
            record = self._required(job_id)
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
            record = replace(
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
                error=snapshot.error,
            )
            self._write(record)
        return record

    def fail_submission(self, job_id: str, error: ProviderErrorDetails) -> ImageJobRecord:
        return self.apply_snapshot(
            job_id,
            ProviderSnapshot("failed", None, error=error, phase="failed"),
        )

    def median_duration_seconds(self, record: ImageJobRecord, limit: int = 10) -> float | None:
        face_clause = (
            "face_reference_path IS NOT NULL"
            if record.face_reference_path
            else "face_reference_path IS NULL"
        )
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT started_at, completed_at FROM image_jobs
                WHERE status = 'completed' AND operation = ? AND aspect_ratio = ?
                  AND {face_clause} AND started_at IS NOT NULL AND completed_at IS NOT NULL
                  AND id != ?
                ORDER BY completed_at DESC LIMIT ?
                """,
                (record.operation, record.aspect_ratio, record.id, max(1, min(limit, 30))),
            ).fetchall()
        durations = [
            (
                self._parse_datetime(row["completed_at"])
                - self._parse_datetime(row["started_at"])
            ).total_seconds()
            for row in rows
        ]
        return float(median(durations)) if durations else None

    def _required(self, job_id: str) -> ImageJobRecord:
        row = self._connection.execute(
            "SELECT * FROM image_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ImageJobNotFoundError(job_id)
        return self._from_row(row)

    def _write(self, record: ImageJobRecord) -> None:
        result = record.result
        error = record.error
        self._connection.execute(
            """
            INSERT INTO image_jobs (
                id, prompt, aspect_ratio, style, seed, provider, operation,
                source_path, source_job_id, face_reference_path, edit_settings_json, created_at,
                provider_job_id, status, progress, phase, current_step, total_steps,
                progress_source, progress_updated_at, stalled, started_at, completed_at,
                result_mime_type, result_width, result_height, result_path,
                error_code, error_message, error_action, error_retryable, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                prompt = excluded.prompt,
                aspect_ratio = excluded.aspect_ratio,
                style = excluded.style,
                seed = excluded.seed,
                provider = excluded.provider,
                operation = excluded.operation,
                source_path = excluded.source_path,
                source_job_id = excluded.source_job_id,
                face_reference_path = excluded.face_reference_path,
                edit_settings_json = excluded.edit_settings_json,
                provider_job_id = excluded.provider_job_id,
                status = excluded.status,
                progress = excluded.progress,
                phase = excluded.phase,
                current_step = excluded.current_step,
                total_steps = excluded.total_steps,
                progress_source = excluded.progress_source,
                progress_updated_at = excluded.progress_updated_at,
                stalled = excluded.stalled,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at,
                result_mime_type = excluded.result_mime_type,
                result_width = excluded.result_width,
                result_height = excluded.result_height,
                result_path = excluded.result_path,
                error_code = excluded.error_code,
                error_message = excluded.error_message,
                error_action = excluded.error_action,
                error_retryable = excluded.error_retryable,
                updated_at = excluded.updated_at
            """,
            (
                record.id,
                record.prompt,
                record.aspect_ratio,
                record.style,
                record.seed,
                record.provider,
                record.operation,
                record.source_path,
                record.source_job_id,
                record.face_reference_path,
                self._serialize_edit_settings(record.edit_settings),
                self._format_datetime(record.created_at),
                record.provider_job_id,
                record.status,
                record.progress,
                record.phase,
                record.current_step,
                record.total_steps,
                record.progress_source,
                self._format_datetime(record.progress_updated_at),
                int(record.stalled),
                self._format_datetime(record.started_at),
                self._format_datetime(record.completed_at),
                result.mime_type if result else None,
                result.width if result else None,
                result.height if result else None,
                record.result_path,
                error.code if error else None,
                error.message if error else None,
                error.action if error else None,
                int(error.retryable) if error else None,
                self._format_datetime(self.now()),
            ),
        )
        self._connection.commit()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ImageJobRecord:
        result = None
        if row["result_mime_type"] is not None:
            result = ProviderResult(
                cast(ImageMimeType, row["result_mime_type"]),
                cast(int, row["result_width"]),
                cast(int, row["result_height"]),
            )
        error = None
        if row["error_code"] is not None:
            error = ProviderErrorDetails(
                cast(str, row["error_code"]),
                cast(str, row["error_message"]),
                cast(str, row["error_action"]),
                bool(row["error_retryable"]),
            )
        return ImageJobRecord(
            id=cast(str, row["id"]),
            prompt=cast(str, row["prompt"]),
            aspect_ratio=cast(AspectRatio, row["aspect_ratio"]),
            style=cast(ImageStyle, row["style"]),
            seed=cast(int, row["seed"]),
            provider=cast(ImageProviderName, row["provider"]),
            created_at=ImageJobRepository._parse_datetime(row["created_at"]),
            operation=cast(ImageJobOperation, row["operation"]),
            source_path=cast(str | None, row["source_path"]),
            source_job_id=cast(str | None, row["source_job_id"]),
            face_reference_path=cast(str | None, row["face_reference_path"]),
            edit_settings=ImageJobRepository._parse_edit_settings(row["edit_settings_json"]),
            provider_job_id=cast(str | None, row["provider_job_id"]),
            status=cast(ImageJobStatus, row["status"]),
            progress=cast(int | None, row["progress"]),
            phase=cast(ImageProgressPhase, row["phase"]),
            current_step=cast(int | None, row["current_step"]),
            total_steps=cast(int | None, row["total_steps"]),
            progress_source=cast(ImageProgressSource, row["progress_source"]),
            progress_updated_at=ImageJobRepository._parse_optional_datetime(
                row["progress_updated_at"]
            ),
            stalled=bool(row["stalled"]),
            started_at=ImageJobRepository._parse_optional_datetime(row["started_at"]),
            completed_at=ImageJobRepository._parse_optional_datetime(row["completed_at"]),
            result=result,
            result_path=cast(str | None, row["result_path"]),
            error=error,
        )

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("Stored job timestamp is invalid.")
        return datetime.fromisoformat(value)

    @staticmethod
    def _parse_optional_datetime(value: object) -> datetime | None:
        return ImageJobRepository._parse_datetime(value) if value is not None else None

    @staticmethod
    def _serialize_edit_settings(settings: ImageEditSettings | None) -> str | None:
        if settings is None:
            return None
        return json.dumps(
            {
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
            },
            separators=(",", ":"),
        )

    @staticmethod
    def _parse_edit_settings(value: object) -> ImageEditSettings | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            payload = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
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
                for item in payload.get("loras", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ),
        )
