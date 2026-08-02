"""Add durable tags for Library assets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_library_tags"
down_revision: str | None = "0002_generation_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_job_tags",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("tag", sa.String(length=48), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["image_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "tag"),
    )
    op.create_index(
        "ix_image_job_tags_tag_job",
        "image_job_tags",
        ["tag", "job_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_image_job_tags_tag_job", table_name="image_job_tags")
    op.drop_table("image_job_tags")
