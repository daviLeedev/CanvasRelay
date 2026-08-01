"""Create the durable image job metadata store."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_image_jobs"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "image_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=16), nullable=False),
        sa.Column("style", sa.String(length=32), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("source_path", sa.Text()),
        sa.Column("source_job_id", sa.String(length=64)),
        sa.Column("face_reference_path", sa.Text()),
        sa.Column("edit_settings_json", json_type),
        sa.Column("provider_metadata_json", json_type),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_job_id", sa.String(length=128)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer()),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("current_step", sa.Integer()),
        sa.Column("total_steps", sa.Integer()),
        sa.Column("progress_source", sa.String(length=32), nullable=False),
        sa.Column("progress_updated_at", sa.DateTime(timezone=True)),
        sa.Column("stalled", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("result_mime_type", sa.String(length=64)),
        sa.Column("result_width", sa.Integer()),
        sa.Column("result_height", sa.Integer()),
        sa.Column("result_path", sa.Text()),
        sa.Column("thumbnail_path", sa.Text()),
        sa.Column("result_size_bytes", sa.Integer()),
        sa.Column("result_sha256", sa.String(length=64)),
        sa.Column("result_missing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("error_action", sa.Text()),
        sa.Column("error_retryable", sa.Boolean()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_job_id"],
            ["image_jobs.id"],
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        "ix_image_jobs_created",
        "image_jobs",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_image_jobs_status_created",
        "image_jobs",
        ["status", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_image_jobs_operation_created",
        "image_jobs",
        ["operation", sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_image_jobs_source_job", "image_jobs", ["source_job_id"])
    op.create_index("ix_image_jobs_provider_job", "image_jobs", ["provider", "provider_job_id"])
    op.create_index(
        "ix_image_jobs_completed_library",
        "image_jobs",
        ["operation", sa.text("created_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("status = 'completed'"),
    )
    op.create_index(
        "ix_image_jobs_active_provider_reconnect",
        "image_jobs",
        ["provider", sa.text("created_at ASC")],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_table("image_jobs")
