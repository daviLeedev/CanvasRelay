from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock

from app.domain.image_jobs import (
    ImageGenerationRequest,
    ImageProviderName,
    ProviderContent,
    ProviderErrorDetails,
    ProviderResult,
    ProviderSnapshot,
    image_dimensions,
    render_demo_svg,
)
from app.providers.base import ImageProviderError, ProviderDescriptor

QUEUE_DURATION = timedelta(milliseconds=750)
RUN_DURATION = timedelta(milliseconds=2750)


class DemoImageProvider:
    name: ImageProviderName = "demo"

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._jobs: dict[str, ImageGenerationRequest] = {}
        self._canceled: set[str] = set()
        self._lock = RLock()

    async def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            "demo",
            "Deterministic demo",
            True,
            "Ready without a GPU or model files.",
        )

    async def submit(self, request: ImageGenerationRequest) -> str:
        with self._lock:
            self._jobs[request.job_id] = request
        return request.job_id

    def resume(self, provider_job_id: str, request: ImageGenerationRequest) -> None:
        with self._lock:
            self._jobs.setdefault(provider_job_id, request)

    async def poll(self, provider_job_id: str) -> ProviderSnapshot:
        request = self._get(provider_job_id)
        with self._lock:
            if provider_job_id in self._canceled:
                return ProviderSnapshot("canceled", 0)
        queued_until = request.created_at + QUEUE_DURATION
        completed_at = queued_until + RUN_DURATION
        now = self._clock()
        if now < queued_until:
            return ProviderSnapshot("queued", 0)
        if now < completed_at:
            elapsed = (now - queued_until).total_seconds()
            fraction = elapsed / RUN_DURATION.total_seconds()
            return ProviderSnapshot("running", min(95, 8 + round(fraction * 87)))
        width, height = image_dimensions(request.aspect_ratio)
        return ProviderSnapshot("completed", 100, ProviderResult("image/svg+xml", width, height))

    async def cancel(self, provider_job_id: str) -> ProviderSnapshot:
        self._get(provider_job_id)
        with self._lock:
            self._canceled.add(provider_job_id)
        return ProviderSnapshot("canceled", 0)

    async def collect(self, provider_job_id: str) -> ProviderContent:
        request = self._get(provider_job_id)
        snapshot = await self.poll(provider_job_id)
        if snapshot.status != "completed":
            raise ImageProviderError(
                details=ProviderErrorDetails(
                    "result_not_ready",
                    "The demo result is not ready yet.",
                    "Wait for generation to complete and try again.",
                    True,
                )
            )
        return ProviderContent(render_demo_svg(request).encode(), "image/svg+xml")

    def _get(self, provider_job_id: str) -> ImageGenerationRequest:
        with self._lock:
            request = self._jobs.get(provider_job_id)
        if request is None:
            raise ImageProviderError(
                details=ProviderErrorDetails(
                    "provider_job_missing",
                    "The demo job is no longer available.",
                    "Create a new image job.",
                    False,
                )
            )
        return request
