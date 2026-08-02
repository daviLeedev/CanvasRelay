"""Persist advanced image generation settings."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_generation_settings"
down_revision: str | None = "0001_image_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("image_jobs", sa.Column("generation_settings_json", json_type))


def downgrade() -> None:
    op.drop_column("image_jobs", "generation_settings_json")
