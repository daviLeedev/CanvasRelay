import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.cli.import_sqlite import import_sqlite
from app.repositories.database import Base, create_database_engine
from app.repositories.image_jobs import ImageJobRepository


@pytest.mark.postgres
def test_postgres_repository_uses_the_sqlite_contract() -> None:
    database_url = os.getenv("CANVASRELAY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("CANVASRELAY_TEST_DATABASE_URL is not configured.")
    engine = create_database_engine(database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    current = datetime(2026, 8, 1, tzinfo=UTC)
    repository = ImageJobRepository(lambda: current, engine=engine, create_schema=False)
    try:
        first = repository.create(
            prompt="First",
            aspect_ratio="1:1",
            style="editorial",
            seed=1,
            provider="demo",
        )
        current += timedelta(seconds=1)
        second = repository.create(
            prompt="Second",
            aspect_ratio="1:1",
            style="editorial",
            seed=2,
            provider="demo",
            operation="edit",
        )
        repository.attach_inputs(second.id, source_path="source.png", source_job_id=first.id)

        page, cursor = repository.list_page(limit=1)
        next_page, _ = repository.list_page(limit=1, cursor=cursor)

        assert [item.id for item in page] == [second.id]
        assert [item.id for item in next_page] == [first.id]
        assert repository.has_dependents(first.id)
        assert repository.get(second.id).source_job_id == first.id
    finally:
        repository.close()


@pytest.mark.postgres
def test_sqlite_import_into_postgres_is_idempotent(tmp_path: Path) -> None:
    database_url = os.getenv("CANVASRELAY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("CANVASRELAY_TEST_DATABASE_URL is not configured.")
    engine = create_database_engine(database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()
    sqlite_path = tmp_path / "legacy.sqlite3"
    source = ImageJobRepository(database_path=sqlite_path)
    created = source.create(
        prompt="Imported PostgreSQL record",
        aspect_ratio="4:3",
        style="product",
        seed=41,
        provider="demo",
    )
    source.close()

    first = import_sqlite(
        sqlite_path=sqlite_path,
        database_url=database_url,
        data_dir=tmp_path / "data",
        dry_run=False,
    )
    second = import_sqlite(
        sqlite_path=sqlite_path,
        database_url=database_url,
        data_dir=tmp_path / "data",
        dry_run=False,
    )
    target = ImageJobRepository(database_url=database_url, create_schema=False)
    try:
        assert first["imported"] == 1
        assert second["skipped"] == 1
        assert target.get(created.id).created_at == created.created_at
    finally:
        target.close()
