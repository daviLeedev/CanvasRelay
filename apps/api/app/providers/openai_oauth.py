from __future__ import annotations

import asyncio
import base64
import binascii
import json
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

import httpx
from PIL import Image, UnidentifiedImageError

from app.domain.image_jobs import (
    GPTImageSettings,
    ImageGenerationRequest,
    ImageMimeType,
    ImageProviderName,
    ProviderContent,
    ProviderErrorDetails,
    ProviderResult,
    ProviderSnapshot,
)
from app.providers.base import (
    ImageEditProviderOptions,
    ImageGenerationProviderOptions,
    ImageProviderError,
    ProviderDescriptor,
)
from app.providers.codex_connection import CodexConnectionManager


@dataclass(slots=True)
class _OAuthJob:
    request: ImageGenerationRequest
    references: tuple[ProviderContent, ...]
    task: asyncio.Task[tuple[ProviderContent, ...]]
    phase: str = "queued"
    canceled: bool = False


class OpenAIOAuthImageProvider:
    """Experimental image provider routed only through the local owner OAuth proxy."""

    name: ImageProviderName = "openai_oauth"

    def __init__(
        self,
        connection: CodexConnectionManager,
        *,
        timeout_seconds: float = 120.0,
        max_parallel_jobs: int = 2,
        configured_model: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.connection = connection
        self.timeout_seconds = max(10.0, timeout_seconds)
        self.configured_model = configured_model.strip() if configured_model else None
        self._transport = transport
        self._jobs: dict[str, _OAuthJob] = {}
        self._semaphore = asyncio.Semaphore(max(1, min(max_parallel_jobs, 8)))

    async def describe(self) -> ProviderDescriptor:
        status = await self.connection.check()
        return ProviderDescriptor(
            self.name,
            "GPT Image via owner Codex login",
            status.connected,
            status.message,
        )

    async def describe_edit(self) -> ProviderDescriptor:
        return await self.describe()

    async def describe_edit_options(self) -> ImageEditProviderOptions:
        return ImageEditProviderOptions((), (), ())

    async def describe_generation_options(self) -> ImageGenerationProviderOptions:
        return ImageGenerationProviderOptions((), (), ())

    async def submit(self, request: ImageGenerationRequest) -> str:
        return await self.submit_with_references(request, ())

    async def submit_edit(
        self,
        request: ImageGenerationRequest,
        source: ProviderContent,
        face_reference: ProviderContent | None,
    ) -> str:
        references = (source,) if face_reference is None else (source, face_reference)
        return await self.submit_with_references(request, references)

    async def submit_with_references(
        self,
        request: ImageGenerationRequest,
        references: tuple[ProviderContent, ...],
    ) -> str:
        connection = await self.connection.check()
        if not connection.connected:
            raise ImageProviderError(self._connection_error(connection.state))
        provider_job_id = f"oauth_{uuid4().hex}"
        task = asyncio.create_task(self._generate(request, references))
        self._jobs[provider_job_id] = _OAuthJob(request, references, task)
        return provider_job_id

    def resume(self, provider_job_id: str, request: ImageGenerationRequest) -> None:
        # OAuth responses are transient. Persisted terminal results remain in CanvasRelay;
        # an unfinished in-memory request becomes retryable after an API restart.
        del provider_job_id, request

    async def poll(self, provider_job_id: str) -> ProviderSnapshot:
        job = self._jobs.get(provider_job_id)
        if job is None:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "provider_restarted",
                    "The local owner connection restarted before this image finished.",
                    "Your settings were preserved. Retry the image when the provider is ready.",
                    True,
                )
            )
        if job.canceled:
            return ProviderSnapshot("canceled", None, phase="canceled")
        if not job.task.done():
            if job.phase == "queued":
                return ProviderSnapshot("queued", None, phase="queued")
            return ProviderSnapshot("running", None, phase="generating")
        if job.task.cancelled():
            return ProviderSnapshot("canceled", None, phase="canceled")
        error = job.task.exception()
        if error is not None:
            if isinstance(error, ImageProviderError):
                return ProviderSnapshot("failed", None, error=error.details, phase="failed")
            return ProviderSnapshot("failed", None, error=self._generic_error(), phase="failed")
        content = job.task.result()
        if not content:
            return ProviderSnapshot("failed", None, error=self._empty_error(), phase="failed")
        width, height = self._dimensions(content[0])
        return ProviderSnapshot(
            "completed",
            100,
            ProviderResult(content[0].mime_type, width, height),
            phase="completed",
            progress_source="provider",
        )

    async def cancel(self, provider_job_id: str) -> ProviderSnapshot:
        job = self._jobs.get(provider_job_id)
        if job is None:
            raise ImageProviderError(self._missing_error())
        job.canceled = True
        job.task.cancel()
        return ProviderSnapshot("canceled", None, phase="canceled")

    async def collect(self, provider_job_id: str) -> ProviderContent:
        results = await self.collect_many(provider_job_id)
        return results[0]

    async def collect_many(self, provider_job_id: str) -> tuple[ProviderContent, ...]:
        job = self._jobs.get(provider_job_id)
        if job is None:
            raise ImageProviderError(self._missing_error())
        if not job.task.done() or job.task.cancelled():
            raise ImageProviderError(self._not_ready_error())
        try:
            content = job.task.result()
        except ImageProviderError:
            raise
        except Exception as error:
            raise ImageProviderError(self._generic_error()) from error
        if not content:
            raise ImageProviderError(self._empty_error())
        return content

    async def _generate(
        self,
        request: ImageGenerationRequest,
        references: tuple[ProviderContent, ...],
    ) -> tuple[ProviderContent, ...]:
        settings = request.gpt_settings or GPTImageSettings()
        async with self._semaphore:
            job = next(
                (item for item in self._jobs.values() if item.request.job_id == request.job_id),
                None,
            )
            if job is not None:
                job.phase = "preparing"
            model = await self._resolve_model()
            results: list[ProviderContent] = []
            for _ in range(settings.count):
                if job is not None and job.canceled:
                    raise asyncio.CancelledError
                if job is not None:
                    job.phase = "generating"
                results.extend(await self._request_once(request, settings, references, model))
                if len(results) >= settings.count:
                    break
            return tuple(results[: settings.count])

    async def _resolve_model(self) -> str | None:
        if self.configured_model:
            return self.configured_model
        try:
            async with httpx.AsyncClient(
                base_url=self.connection.base_url,
                timeout=4.0,
                transport=self._transport,
            ) as client:
                response = await client.get("/v1/models")
        except httpx.HTTPError:
            return None
        if not response.is_success:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return None
        identifiers = [item.get("id") for item in rows if isinstance(item, dict)]
        image_models = [
            value for value in identifiers if isinstance(value, str) and "image" in value
        ]
        return image_models[0] if image_models else None

    async def _request_once(
        self,
        request: ImageGenerationRequest,
        settings: GPTImageSettings,
        references: tuple[ProviderContent, ...],
        model: str | None,
    ) -> list[ProviderContent]:
        body = self._payload(request, settings, references, model)
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    base_url=self.connection.base_url,
                    timeout=self.timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.post("/v1/responses", json=body)
            except httpx.HTTPError as error:
                raise ImageProviderError(self._network_error()) from error
            if response.status_code in {401, 403}:
                self.connection.mark_reauth_required()
                raise ImageProviderError(self._connection_error("reauth_required"))
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                await asyncio.sleep(0.4 * (2**attempt))
                continue
            if not response.is_success:
                raise ImageProviderError(self._request_error(response.status_code))
            return self._parse_response(response)
        raise ImageProviderError(self._generic_error())

    @staticmethod
    def _payload(
        request: ImageGenerationRequest,
        settings: GPTImageSettings,
        references: tuple[ProviderContent, ...],
        model: str | None,
    ) -> dict[str, object]:
        content: list[dict[str, object]] = [{"type": "input_text", "text": request.prompt}]
        for reference in references:
            content.append(
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{reference.mime_type};base64,"
                        f"{base64.b64encode(reference.body).decode('ascii')}"
                    ),
                }
            )
        image_tool: dict[str, object] = {
            "type": "image_generation",
            "quality": settings.quality,
            "size": settings.size,
            "moderation": settings.moderation,
        }
        payload: dict[str, object] = {
            "input": [{"role": "user", "content": content}],
            "tools": [image_tool],
            "tool_choice": {"type": "image_generation"},
        }
        if model:
            payload["model"] = model
        if settings.reasoning_effort != "none":
            payload["reasoning"] = {"effort": settings.reasoning_effort}
        if settings.web_search:
            payload["tools"] = [
                {"type": "web_search"},
                image_tool,
            ]
        return payload

    def _parse_response(self, response: httpx.Response) -> list[ProviderContent]:
        payload: object
        try:
            payload = response.json()
        except ValueError:
            payload = self._parse_sse(response.text)
        images = self._find_images(payload)
        if not images:
            raise ImageProviderError(self._empty_error())
        return images

    @staticmethod
    def _parse_sse(text: str) -> list[object]:
        events: list[object] = []
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            value = line.removeprefix("data:").strip()
            if not value or value == "[DONE]":
                continue
            try:
                events.append(json.loads(value))
            except json.JSONDecodeError:
                continue
        return events

    def _find_images(self, payload: object) -> list[ProviderContent]:
        values: list[str] = []

        def visit(value: object) -> None:
            if isinstance(value, dict):
                for key in ("result", "image_base64", "b64_json"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate:
                        values.append(candidate)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(payload)
        results: list[ProviderContent] = []
        for value in values:
            candidate = value.split(",", 1)[-1] if value.startswith("data:") else value
            try:
                body = base64.b64decode(candidate, validate=True)
            except (ValueError, binascii.Error):
                continue
            mime_type = self._mime_type(body)
            if mime_type is not None:
                results.append(ProviderContent(body, mime_type))
        return results

    @staticmethod
    def _mime_type(body: bytes) -> ImageMimeType | None:
        if body.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if body.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
            return "image/webp"
        return None

    @staticmethod
    def _dimensions(content: ProviderContent) -> tuple[int, int]:
        try:
            with Image.open(BytesIO(content.body)) as image:
                return image.size
        except (OSError, UnidentifiedImageError):
            return (0, 0)

    @staticmethod
    def _connection_error(state: str) -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "reauth_required" if state == "reauth_required" else "owner_connection_unavailable",
            "The owner GPT connection is not ready.",
            "Sign in to Codex on the owner computer, then check the connection in Settings.",
            state != "reauth_required",
        )

    @staticmethod
    def _network_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "provider_unavailable",
            "The owner GPT connection could not reach the image service.",
            "Check the local connection and try again.",
            True,
        )

    @staticmethod
    def _request_error(status_code: int) -> ProviderErrorDetails:
        if status_code == 429:
            return ProviderErrorDetails(
                "provider_rate_limited",
                "The owner GPT connection is temporarily rate limited.",
                "Wait a moment, then retry the job.",
                True,
            )
        if 400 <= status_code < 500:
            return ProviderErrorDetails(
                "provider_request_rejected",
                "The image service rejected this request.",
                "Review the prompt and selected inputs, then create a new job.",
                False,
            )
        return ProviderErrorDetails(
            "provider_unavailable",
            "The owner GPT connection could not finish the request.",
            "Check the provider status and try again.",
            True,
        )

    @staticmethod
    def _not_ready_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "result_not_ready",
            "The image result is not ready.",
            "Wait for completion and try again.",
            True,
        )

    @staticmethod
    def _missing_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "provider_job_missing",
            "The local owner connection no longer reports this image job.",
            "Create a new job with the saved settings.",
            True,
        )

    @staticmethod
    def _empty_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "provider_empty_response",
            "The image service did not return a usable image.",
            "Try the request again or simplify the prompt.",
            True,
        )

    @staticmethod
    def _generic_error() -> ProviderErrorDetails:
        return ProviderErrorDetails(
            "provider_generation_failed",
            "The image service could not finish the request.",
            "Check the provider status and try again.",
            True,
        )
