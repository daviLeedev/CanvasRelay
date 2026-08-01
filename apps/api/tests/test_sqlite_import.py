from datetime import UTC, datetime
from pathlib import Path

from app.cli.import_sqlite import import_sqlite
from app.domain.image_jobs import ProviderContent, ProviderResult, ProviderSnapshot
from app.repositories.image_jobs import ImageJobRepository
from app.repositories.media import FilesystemMediaStore


def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.resolve().as_posix()}"


def test_sqlite_import_is_idempotent_and_preserves_relations_and_media_metadata(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "legacy.sqlite3"
    target_path = tmp_path / "target.sqlite3"
    data_dir = tmp_path / "data"
    source = ImageJobRepository(lambda: datetime(2026, 8, 1, tzinfo=UTC), source_path)
    target = ImageJobRepository(database_path=target_path)
    media = FilesystemMediaStore(data_dir / "media" / "images")
    parent = source.create(
        prompt="Parent",
        aspect_ratio="1:1",
        style="editorial",
        seed=1,
        provider="demo",
    )
    stored = media.save_with_metadata(
        parent.id,
        ProviderContent(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml"),
    )
    source.apply_snapshot(
        parent.id,
        ProviderSnapshot(
            "completed",
            100,
            result=ProviderResult("image/svg+xml", 64, 64),
            phase="completed",
        ),
        result_path=stored.storage_key,
    )
    child = source.create(
        prompt="Child edit",
        aspect_ratio="1:1",
        style="editorial",
        seed=2,
        provider="demo",
        operation="edit",
    )
    source.attach_inputs(child.id, source_path="missing-source.png", source_job_id=parent.id)
    source.close()
    target.close()

    dry_run = import_sqlite(
        sqlite_path=source_path,
        database_url=sqlite_url(target_path),
        data_dir=data_dir,
        dry_run=True,
    )
    imported = import_sqlite(
        sqlite_path=source_path,
        database_url=sqlite_url(target_path),
        data_dir=data_dir,
        dry_run=False,
    )
    repeated = import_sqlite(
        sqlite_path=source_path,
        database_url=sqlite_url(target_path),
        data_dir=data_dir,
        dry_run=False,
    )

    restored = ImageJobRepository(database_path=target_path)
    try:
        assert dry_run == {"read": 2, "imported": 2, "skipped": 0, "missing": 0}
        assert imported == {"read": 2, "imported": 2, "skipped": 0, "missing": 0}
        assert repeated == {"read": 2, "imported": 0, "skipped": 2, "missing": 0}
        assert restored.get(child.id).source_job_id == parent.id
        restored_parent = restored.get(parent.id)
        assert restored_parent.result_size_bytes == stored.size_bytes
        assert restored_parent.result_sha256 == stored.sha256
        assert not restored_parent.result_missing
    finally:
        restored.close()
