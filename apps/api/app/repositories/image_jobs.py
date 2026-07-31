from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from app.domain.image_jobs import (
    AspectRatio,
    ImageJobRecord,
    ImageStyle,
    calculate_state,
    normalize_prompt,
    resolve_seed,
)


class ImageJobNotFoundError(KeyError):
    pass


class ImageJobRepository:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._records: dict[str, ImageJobRecord] = {}
        self._lock = RLock()

    def now(self) -> datetime:
        return self._clock()

    def create(
        self,
        *,
        prompt: str,
        aspect_ratio: AspectRatio,
        style: ImageStyle,
        seed: int | None,
    ) -> ImageJobRecord:
        normalized_prompt = normalize_prompt(prompt)
        record = ImageJobRecord(
            id=f"img_{uuid4().hex}",
            prompt=normalized_prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=resolve_seed(normalized_prompt, aspect_ratio, style, seed),
            created_at=self.now(),
        )
        with self._lock:
            self._records[record.id] = record
        return record

    def get(self, job_id: str) -> ImageJobRecord:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise ImageJobNotFoundError(job_id)
            return replace(record)

    def cancel(self, job_id: str) -> ImageJobRecord:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise ImageJobNotFoundError(job_id)
            now = self.now()
            if calculate_state(record, now).status == "completed":
                return replace(record)
            if record.canceled_at is None:
                record = replace(record, canceled_at=now)
                self._records[job_id] = record
            return replace(record)
