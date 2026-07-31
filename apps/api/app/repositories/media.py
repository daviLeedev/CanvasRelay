from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from app.domain.image_jobs import ImageMimeType, ProviderContent


class MediaNotFoundError(FileNotFoundError):
    pass


class FilesystemMediaStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, job_id: str, content: ProviderContent) -> str:
        extension = {
            "image/svg+xml": ".svg",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }[content.mime_type]
        filename = f"{job_id}{extension}"
        target = self._resolve(filename)
        temporary = self._resolve(f".{filename}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content.body)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return filename

    def read(self, relative_path: str, mime_type: ImageMimeType) -> ProviderContent:
        path = self._resolve(relative_path)
        try:
            return ProviderContent(path.read_bytes(), mime_type)
        except FileNotFoundError as error:
            raise MediaNotFoundError(relative_path) from error

    def _resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if path.parent != self.root:
            raise ValueError("Media path escapes the configured storage root.")
        return path


class FilesystemUploadStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, job_id: str, role: str, content: ProviderContent) -> str:
        if role not in {"source", "face"}:
            raise ValueError("Unsupported upload role.")
        extension = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }[content.mime_type]
        filename = f"{job_id}_{role}{extension}"
        target = self._resolve(filename)
        temporary = self._resolve(f".{filename}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content.body)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return filename

    def _resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if path.parent != self.root:
            raise ValueError("Upload path escapes the configured storage root.")
        return path
