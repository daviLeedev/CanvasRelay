from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


json_type = JSON().with_variant(JSONB(), "postgresql")


class ImageJobRow(Base):
    __tablename__ = "image_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text)
    aspect_ratio: Mapped[str] = mapped_column(String(16))
    style: Mapped[str] = mapped_column(String(32))
    seed: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(32), default="generate")
    source_path: Mapped[str | None] = mapped_column(Text)
    source_job_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("image_jobs.id", ondelete="RESTRICT", deferrable=True, initially="DEFERRED"),
    )
    face_reference_path: Mapped[str | None] = mapped_column(Text)
    edit_settings_json: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    provider_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_job_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    progress: Mapped[int | None] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(32), default="queued")
    current_step: Mapped[int | None] = mapped_column(Integer)
    total_steps: Mapped[int | None] = mapped_column(Integer)
    progress_source: Mapped[str] = mapped_column(String(32), default="unknown")
    progress_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stalled: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_mime_type: Mapped[str | None] = mapped_column(String(64))
    result_width: Mapped[int | None] = mapped_column(Integer)
    result_height: Mapped[int | None] = mapped_column(Integer)
    result_path: Mapped[str | None] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    result_size_bytes: Mapped[int | None] = mapped_column(Integer)
    result_sha256: Mapped[str | None] = mapped_column(String(64))
    result_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_action: Mapped[str | None] = mapped_column(Text)
    error_retryable: Mapped[bool | None] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_image_jobs_created", created_at.desc(), id.desc()),
        Index("ix_image_jobs_status_created", status, created_at.desc(), id.desc()),
        Index("ix_image_jobs_operation_created", operation, created_at.desc(), id.desc()),
        Index("ix_image_jobs_source_job", source_job_id),
        Index("ix_image_jobs_provider_job", provider, provider_job_id),
    )


def create_database_engine(
    database_url: str,
    *,
    pool_size: int = 5,
    max_overflow: int = 10,
) -> Engine:
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite+pysqlite://"} or ":memory:" in database_url:
            options["poolclass"] = StaticPool
    else:
        options["pool_size"] = pool_size
        options["max_overflow"] = max_overflow
    return create_engine(database_url, **options)
