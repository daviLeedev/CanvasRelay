from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.core.config import Settings
from app.domain.image_jobs import (
    AspectRatio,
    ImageJobOperation,
    ImageJobRecord,
    ImageJobStatus,
    ImageMimeType,
    ImageProgressPhase,
    ImageProgressSource,
    ImageProviderName,
    ImageStyle,
    ProviderErrorDetails,
    ProviderResult,
)
from app.repositories.image_jobs import ImageJobRepository
from app.repositories.media import FilesystemMediaStore, MediaNotFoundError


def _value(row: sqlite3.Row, columns: set[str], name: str, default: object = None) -> object:
    return row[name] if name in columns else default


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _json_object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], parsed) if isinstance(parsed, dict) else None


def _integer(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, (int, str)) else default


def read_legacy_records(sqlite_path: Path) -> list[ImageJobRecord]:
    connection = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        columns = {
            cast(str, row["name"])
            for row in connection.execute("PRAGMA table_info(image_jobs)").fetchall()
        }
        if not columns:
            return []
        rows = connection.execute(
            "SELECT * FROM image_jobs ORDER BY created_at ASC, id ASC"
        ).fetchall()
    finally:
        connection.close()

    records: list[ImageJobRecord] = []
    for row in rows:
        result = None
        if (mime := _value(row, columns, "result_mime_type")) is not None:
            result = ProviderResult(
                cast(ImageMimeType, mime),
                _integer(_value(row, columns, "result_width", 0)),
                _integer(_value(row, columns, "result_height", 0)),
            )
        error = None
        if (code := _value(row, columns, "error_code")) is not None:
            error = ProviderErrorDetails(
                str(code),
                str(_value(row, columns, "error_message", "The image job failed.")),
                str(_value(row, columns, "error_action", "Retry the job.")),
                bool(_value(row, columns, "error_retryable", False)),
            )
        created_at = _datetime(_value(row, columns, "created_at"))
        if created_at is None:
            continue
        records.append(
            ImageJobRecord(
                id=str(row["id"]),
                prompt=str(row["prompt"]),
                aspect_ratio=cast(AspectRatio, row["aspect_ratio"]),
                style=cast(ImageStyle, row["style"]),
                seed=int(row["seed"]),
                provider=cast(ImageProviderName, row["provider"]),
                created_at=created_at,
                operation=cast(
                    ImageJobOperation, _value(row, columns, "operation", "generate")
                ),
                source_path=cast(str | None, _value(row, columns, "source_path")),
                source_job_id=cast(str | None, _value(row, columns, "source_job_id")),
                face_reference_path=cast(
                    str | None, _value(row, columns, "face_reference_path")
                ),
                edit_settings=ImageJobRepository._parse_edit_settings(
                    _value(row, columns, "edit_settings_json")
                ),
                provider_job_id=cast(str | None, _value(row, columns, "provider_job_id")),
                status=cast(ImageJobStatus, _value(row, columns, "status", "failed")),
                progress=cast(int | None, _value(row, columns, "progress")),
                phase=cast(ImageProgressPhase, _value(row, columns, "phase", "failed")),
                current_step=cast(int | None, _value(row, columns, "current_step")),
                total_steps=cast(int | None, _value(row, columns, "total_steps")),
                progress_source=cast(
                    ImageProgressSource, _value(row, columns, "progress_source", "unknown")
                ),
                progress_updated_at=_datetime(
                    _value(row, columns, "progress_updated_at")
                ),
                stalled=bool(_value(row, columns, "stalled", False)),
                started_at=_datetime(_value(row, columns, "started_at")),
                completed_at=_datetime(_value(row, columns, "completed_at")),
                result=result,
                result_path=cast(str | None, _value(row, columns, "result_path")),
                thumbnail_path=cast(str | None, _value(row, columns, "thumbnail_path")),
                result_size_bytes=cast(
                    int | None, _value(row, columns, "result_size_bytes")
                ),
                result_sha256=cast(str | None, _value(row, columns, "result_sha256")),
                result_missing=bool(_value(row, columns, "result_missing", False)),
                provider_metadata=_json_object(
                    _value(row, columns, "provider_metadata_json")
                ),
                error=error,
            )
        )
    return records


def import_sqlite(
    *,
    sqlite_path: Path,
    database_url: str,
    data_dir: Path,
    dry_run: bool,
) -> dict[str, int]:
    records = read_legacy_records(sqlite_path)
    repository = ImageJobRepository(database_url=database_url, create_schema=False)
    media_store = FilesystemMediaStore(
        data_dir / "media" / "images",
        data_dir / "media" / "thumbnails",
    )
    summary = {"read": len(records), "imported": 0, "skipped": 0, "missing": 0}
    pending_relations: list[ImageJobRecord] = []
    try:
        for record in records:
            if repository.exists(record.id):
                summary["skipped"] += 1
                continue
            thumbnail_path = record.thumbnail_path
            size_bytes = record.result_size_bytes
            checksum = record.result_sha256
            missing = record.result_missing
            if record.result_path is not None and record.result is not None:
                try:
                    stored = media_store.describe(record.result_path, record.result.mime_type)
                    size_bytes = stored.size_bytes
                    checksum = stored.sha256
                    if not dry_run:
                        thumbnail_path = media_store.ensure_thumbnail(
                            record.result_path, record.result.mime_type
                        )
                    missing = False
                except (MediaNotFoundError, ValueError):
                    missing = True
                    summary["missing"] += 1
            prepared = replace(
                record,
                source_job_id=None,
                thumbnail_path=thumbnail_path,
                result_size_bytes=size_bytes,
                result_sha256=checksum,
                result_missing=missing,
            )
            if not dry_run:
                repository.upsert(prepared)
                pending_relations.append(record)
            summary["imported"] += 1
        if not dry_run:
            for original in pending_relations:
                if original.source_job_id is not None:
                    repository.upsert(
                        replace(repository.get(original.id), source_job_id=original.source_job_id)
                    )
    finally:
        repository.close()
    return summary


def main() -> None:
    settings = Settings()
    parser = argparse.ArgumentParser(description="Import CanvasRelay SQLite jobs into PostgreSQL.")
    parser.add_argument("--sqlite", type=Path, default=settings.database_path)
    parser.add_argument("--database-url", default=settings.resolved_database_url)
    parser.add_argument("--data-dir", type=Path, default=settings.resolved_data_dir)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    summary = import_sqlite(
        sqlite_path=args.sqlite.resolve(),
        database_url=args.database_url,
        data_dir=args.data_dir.resolve(),
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
