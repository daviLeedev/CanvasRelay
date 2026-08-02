from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from app.domain.image_jobs import ImageMimeType, ProviderContent


class MediaNotFoundError(FileNotFoundError):
    pass


@dataclass(frozen=True, slots=True)
class StoredMediaFile:
    path: Path
    storage_key: str
    mime_type: str
    size_bytes: int
    sha256: str

    @property
    def etag(self) -> str:
        return f'"sha256-{self.sha256}"'


@dataclass(frozen=True, slots=True)
class StagedFileDeletion:
    original: Path
    quarantined: Path


class FilesystemMediaStore:
    def __init__(self, root: Path, thumbnail_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.thumbnail_root = (
            thumbnail_root.resolve()
            if thumbnail_root is not None
            else self.root.parent / "thumbnails"
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.thumbnail_root.mkdir(parents=True, exist_ok=True)

    def save(self, job_id: str, content: ProviderContent) -> str:
        return self.save_with_metadata(job_id, content).storage_key

    def save_with_metadata(self, job_id: str, content: ProviderContent) -> StoredMediaFile:
        extension = self._extension(content.mime_type)
        digest = sha256(content.body).hexdigest()
        storage_key = f"{job_id}{extension}"
        target = self._resolve(storage_key)
        if target.exists():
            existing = self.describe(storage_key, content.mime_type)
            if existing.sha256 == digest:
                return existing
            storage_key = f"{job_id}_{uuid4().hex[:12]}{extension}"
            target = self._resolve(storage_key)
        self._atomic_write(target, content.body)
        return StoredMediaFile(target, storage_key, content.mime_type, len(content.body), digest)

    def ensure_thumbnail(
        self,
        relative_path: str,
        mime_type: ImageMimeType,
        *,
        max_edge: int = 400,
    ) -> str | None:
        if mime_type == "image/svg+xml":
            return None
        source = self._resolve(relative_path)
        if not source.is_file():
            raise MediaNotFoundError(relative_path)
        thumbnail_key = f"{Path(relative_path).stem}.webp"
        target = self._resolve_thumbnail(thumbnail_key)
        if target.is_file() and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
            return thumbnail_key
        temporary = self._resolve_thumbnail(f".{thumbnail_key}.{uuid4().hex}.tmp")
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
                image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                image.save(temporary, format="WEBP", quality=84, method=4)
            os.replace(temporary, target)
        except (OSError, UnidentifiedImageError):
            temporary.unlink(missing_ok=True)
            return None
        return thumbnail_key

    def describe(self, relative_path: str, mime_type: str) -> StoredMediaFile:
        path = self._resolve(relative_path)
        return self._describe_path(path, relative_path, mime_type)

    def describe_thumbnail(self, relative_path: str) -> StoredMediaFile:
        path = self._resolve_thumbnail(relative_path)
        return self._describe_path(path, relative_path, "image/webp")

    def read(self, relative_path: str, mime_type: ImageMimeType) -> ProviderContent:
        item = self.describe(relative_path, mime_type)
        try:
            return ProviderContent(item.path.read_bytes(), mime_type)
        except FileNotFoundError as error:
            raise MediaNotFoundError(relative_path) from error

    def delete(self, relative_path: str) -> None:
        self._resolve(relative_path).unlink(missing_ok=True)

    def delete_thumbnail(self, relative_path: str | None) -> None:
        if relative_path is not None:
            self._resolve_thumbnail(relative_path).unlink(missing_ok=True)

    def stage_delete(self, relative_path: str) -> StagedFileDeletion | None:
        return self._stage_path(self._resolve(relative_path), self.root)

    def stage_thumbnail_delete(self, relative_path: str | None) -> StagedFileDeletion | None:
        if relative_path is None:
            return None
        return self._stage_path(self._resolve_thumbnail(relative_path), self.thumbnail_root)

    @staticmethod
    def restore_delete(staged: StagedFileDeletion | None) -> None:
        if staged is not None and staged.quarantined.exists():
            staged.original.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged.quarantined, staged.original)

    @staticmethod
    def finalize_delete(staged: StagedFileDeletion | None) -> None:
        if staged is not None:
            staged.quarantined.unlink(missing_ok=True)

    @staticmethod
    def _stage_path(path: Path, root: Path) -> StagedFileDeletion | None:
        if not path.exists():
            return None
        trash = root / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        quarantined = trash / f"{uuid4().hex}_{path.name}"
        os.replace(path, quarantined)
        return StagedFileDeletion(path, quarantined)

    def _describe_path(self, path: Path, storage_key: str, mime_type: str) -> StoredMediaFile:
        try:
            size = path.stat().st_size
            digest = self._hash_file(path)
        except FileNotFoundError as error:
            raise MediaNotFoundError(storage_key) from error
        return StoredMediaFile(path, storage_key, mime_type, size, digest)

    @staticmethod
    def _atomic_write(target: Path, body: bytes) -> None:
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _extension(mime_type: ImageMimeType) -> str:
        return {
            "image/svg+xml": ".svg",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }[mime_type]

    def _resolve(self, relative_path: str) -> Path:
        return self._secure_resolve(self.root, relative_path, "Media")

    def _resolve_thumbnail(self, relative_path: str) -> Path:
        return self._secure_resolve(self.thumbnail_root, relative_path, "Thumbnail")

    @staticmethod
    def _secure_resolve(root: Path, relative_path: str, label: str) -> Path:
        key = PurePosixPath(relative_path)
        if key.is_absolute() or ".." in key.parts or not key.parts:
            raise ValueError(f"{label} path escapes the configured storage root.")
        path = (root / Path(*key.parts)).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"{label} path escapes the configured storage root.")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class FilesystemUploadStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        job_id: str,
        role: str,
        content: ProviderContent,
        *,
        ordinal: int = 0,
    ) -> str:
        if role not in {"source", "face", "reference"} or ordinal < 0:
            raise ValueError("Unsupported upload role.")
        extension = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }[content.mime_type]
        suffix = f"_{ordinal}" if role == "reference" else ""
        filename = f"{job_id}_{role}{suffix}{extension}"
        target = self._resolve(filename)
        if target.exists():
            filename = f"{job_id}_{role}_{uuid4().hex[:12]}{extension}"
            target = self._resolve(filename)
        FilesystemMediaStore._atomic_write(target, content.body)
        return filename

    def describe(self, relative_path: str, mime_type: str) -> StoredMediaFile:
        path = self._resolve(relative_path)
        try:
            return StoredMediaFile(
                path,
                relative_path,
                mime_type,
                path.stat().st_size,
                FilesystemMediaStore._hash_file(path),
            )
        except FileNotFoundError as error:
            raise MediaNotFoundError(relative_path) from error

    def read(self, relative_path: str, mime_type: ImageMimeType) -> ProviderContent:
        item = self.describe(relative_path, mime_type)
        return ProviderContent(item.path.read_bytes(), mime_type)

    def delete(self, relative_path: str) -> None:
        self._resolve(relative_path).unlink(missing_ok=True)

    def stage_delete(self, relative_path: str) -> StagedFileDeletion | None:
        return FilesystemMediaStore._stage_path(self._resolve(relative_path), self.root)

    def _resolve(self, relative_path: str) -> Path:
        return FilesystemMediaStore._secure_resolve(self.root, relative_path, "Upload")
