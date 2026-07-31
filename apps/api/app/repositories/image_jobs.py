from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from app.domain.image_jobs import (
    AspectRatio,
    ImageJobRecord,
    ImageProviderName,
    ImageStyle,
    ProviderErrorDetails,
    ProviderSnapshot,
    normalize_prompt,
    resolve_seed,
)

TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled"})


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
        provider: ImageProviderName,
    ) -> ImageJobRecord:
        normalized_prompt = normalize_prompt(prompt)
        record = ImageJobRecord(
            id=f"img_{uuid4().hex}",
            prompt=normalized_prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=resolve_seed(normalized_prompt, aspect_ratio, style, seed),
            provider=provider,
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

    def attach_provider_job(self, job_id: str, provider_job_id: str) -> ImageJobRecord:
        with self._lock:
            record = self._required(job_id)
            record = replace(record, provider_job_id=provider_job_id)
            self._records[job_id] = record
            return replace(record)

    def apply_snapshot(self, job_id: str, snapshot: ProviderSnapshot) -> ImageJobRecord:
        with self._lock:
            record = self._required(job_id)
            if record.status in TERMINAL_STATUSES:
                return replace(record)
            now = self.now()
            started_at = record.started_at
            if snapshot.status == "running" and started_at is None:
                started_at = now
            completed_at = record.completed_at
            if snapshot.status in TERMINAL_STATUSES and completed_at is None:
                completed_at = now
            record = replace(
                record,
                status=snapshot.status,
                progress=snapshot.progress,
                started_at=started_at,
                completed_at=completed_at,
                result=snapshot.result,
                error=snapshot.error,
            )
            self._records[job_id] = record
            return replace(record)

    def fail_submission(self, job_id: str, error: ProviderErrorDetails) -> ImageJobRecord:
        return self.apply_snapshot(job_id, ProviderSnapshot("failed", None, error=error))

    def _required(self, job_id: str) -> ImageJobRecord:
        record = self._records.get(job_id)
        if record is None:
            raise ImageJobNotFoundError(job_id)
        return record
