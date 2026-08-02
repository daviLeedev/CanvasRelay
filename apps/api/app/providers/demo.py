from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from threading import RLock

from app.domain.image_jobs import (
    ImageGenerationRequest,
    ImageGenerationSettings,
    ImageProviderName,
    ProviderContent,
    ProviderErrorDetails,
    ProviderResult,
    ProviderSnapshot,
    image_dimensions,
    render_demo_svg,
)
from app.providers.base import (
    ImageEditProviderOptions,
    ImageGenerationProviderOptions,
    ImageProviderError,
    LoraOption,
    ProviderDescriptor,
)

QUEUE_DURATION = timedelta(milliseconds=750)
RUN_DURATION = timedelta(milliseconds=2750)
PREPARE_DURATION = timedelta(milliseconds=500)


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

    async def describe_edit(self) -> ProviderDescriptor:
        return await self.describe()

    async def describe_edit_options(self) -> ImageEditProviderOptions:
        return ImageEditProviderOptions(
            samplers=("euler", "dpmpp_2m"),
            schedulers=("simple", "karras"),
            loras=(
                LoraOption("demo-detail", "Detail enhancer"),
                LoraOption("demo-light", "Studio lighting"),
            ),
        )

    async def describe_generation_options(self) -> ImageGenerationProviderOptions:
        return ImageGenerationProviderOptions(
            samplers=("euler", "dpmpp_2m"),
            schedulers=("beta", "simple", "karras"),
            loras=(
                LoraOption("demo-detail", "Detail enhancer"),
                LoraOption("demo-light", "Studio lighting"),
            ),
        )

    async def submit(self, request: ImageGenerationRequest) -> str:
        with self._lock:
            self._jobs[request.job_id] = request
        return request.job_id

    async def submit_edit(
        self,
        request: ImageGenerationRequest,
        source: ProviderContent,
        face_reference: ProviderContent | None,
    ) -> str:
        del source, face_reference
        return await self.submit(request)

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
            return ProviderSnapshot(
                "queued",
                0,
                phase="queued",
                progress_source="inferred",
                progress_updated_at=now,
            )
        preparing_until = queued_until + PREPARE_DURATION
        if now < preparing_until:
            return ProviderSnapshot(
                "running",
                None,
                phase="preparing",
                progress_source="inferred",
                progress_updated_at=now,
            )
        if now < completed_at:
            elapsed = (now - preparing_until).total_seconds()
            sampling_duration = (RUN_DURATION - PREPARE_DURATION).total_seconds()
            fraction = max(0.0, min(1.0, elapsed / sampling_duration))
            settings = (
                request.generation_settings
                or request.edit_settings
                or ImageGenerationSettings()
            )
            total_steps = settings.steps
            current_step = max(1, min(total_steps, round(fraction * total_steps)))
            return ProviderSnapshot(
                "running",
                min(95, round(fraction * 95)),
                phase="sampling",
                current_step=current_step,
                total_steps=total_steps,
                progress_source="provider",
                progress_updated_at=now,
            )
        width, height = image_dimensions(request.aspect_ratio)
        return ProviderSnapshot(
            "completed",
            100,
            ProviderResult("image/svg+xml", width, height),
            phase="completed",
            progress_source="provider",
            progress_updated_at=now,
        )

    async def cancel(self, provider_job_id: str) -> ProviderSnapshot:
        self._get(provider_job_id)
        with self._lock:
            self._canceled.add(provider_job_id)
        return ProviderSnapshot("canceled", 0, phase="canceled", progress_source="provider")

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
