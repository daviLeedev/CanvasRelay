"""Add durable GPT input and output asset metadata."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_gpt_job_assets"
down_revision: str | None = "0003_library_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("image_jobs", sa.Column("gpt_settings_json", sa.JSON(), nullable=True))
    op.create_table(
        "image_job_inputs",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["image_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "role", "ordinal"),
    )
    op.create_index(
        "ix_image_job_inputs_job_role",
        "image_job_inputs",
        ["job_id", "role", "ordinal"],
        unique=False,
    )
    op.create_table(
        "image_job_assets",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("thumbnail_key", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["image_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "ordinal"),
    )
    op.create_index(
        "ix_image_job_assets_job_ordinal",
        "image_job_assets",
        ["job_id", "ordinal"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_image_job_assets_job_ordinal", table_name="image_job_assets")
    op.drop_table("image_job_assets")
    op.drop_index("ix_image_job_inputs_job_role", table_name="image_job_inputs")
    op.drop_table("image_job_inputs")
    op.drop_column("image_jobs", "gpt_settings_json")
