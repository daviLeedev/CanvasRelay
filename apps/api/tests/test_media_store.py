from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.domain.image_jobs import ProviderContent
from app.repositories.media import FilesystemMediaStore


def png_bytes(size: tuple[int, int] = (1200, 800)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (42, 91, 118)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_media_store_persists_checksum_and_webp_thumbnail(tmp_path: Path) -> None:
    store = FilesystemMediaStore(tmp_path / "images", tmp_path / "thumbnails")

    stored = store.save_with_metadata(
        "img_thumbnail",
        ProviderContent(png_bytes(), "image/png"),
    )
    thumbnail_key = store.ensure_thumbnail(stored.storage_key, "image/png")

    assert stored.size_bytes > 0
    assert len(stored.sha256) == 64
    assert thumbnail_key == "img_thumbnail.webp"
    thumbnail = store.describe_thumbnail(thumbnail_key)
    assert thumbnail.mime_type == "image/webp"
    with Image.open(thumbnail.path) as image:
        assert max(image.size) <= 400


def test_media_store_never_overwrites_different_content(tmp_path: Path) -> None:
    store = FilesystemMediaStore(tmp_path / "images")
    first = store.save_with_metadata(
        "img_unique",
        ProviderContent(png_bytes((10, 10)), "image/png"),
    )
    second = store.save_with_metadata(
        "img_unique",
        ProviderContent(png_bytes((20, 20)), "image/png"),
    )

    assert first.storage_key != second.storage_key
    assert first.path.read_bytes() != second.path.read_bytes()


@pytest.mark.parametrize("storage_key", ["../secret.png", "/secret.png", "a/../../b.png"])
def test_media_store_blocks_path_traversal(tmp_path: Path, storage_key: str) -> None:
    store = FilesystemMediaStore(tmp_path / "images")

    with pytest.raises(ValueError, match="escapes"):
        store.describe(storage_key, "image/png")
