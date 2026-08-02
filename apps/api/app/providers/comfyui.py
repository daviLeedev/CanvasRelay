from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, cast
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

import httpx
from websockets.asyncio.client import connect

from app.domain.image_jobs import (
    ImageGenerationRequest,
    ImageJobStatus,
    ImageMimeType,
    ImageProgressPhase,
    ImageProviderName,
    LoraSelection,
    ProviderContent,
    ProviderErrorDetails,
    ProviderResult,
    ProviderSnapshot,
    image_dimensions,
)
from app.providers.base import (
    ImageEditProviderOptions,
    ImageGenerationProviderOptions,
    ImageProviderError,
    LoraOption,
    ProviderDescriptor,
)

PLACEHOLDERS = {
    "{{prompt}}",
    "{{seed}}",
    "{{width}}",
    "{{height}}",
    "{{filename_prefix}}",
}
EDIT_PLACEHOLDERS = PLACEHOLDERS | {"{{source_image}}"}
@dataclass(slots=True)
class _TrackedComfyJob:
    request: ImageGenerationRequest
    submitted_at: datetime
    last_status: ImageJobStatus = "queued"
    missing_polls: int = 0
    phase: ImageProgressPhase = "queued"
    current_step: int | None = None
    total_steps: int | None = None
    last_event_at: datetime | None = None
    websocket_available: bool = False


@dataclass(frozen=True, slots=True)
class _LoraAllowlistEntry:
    id: str
    label: str
    filename: str


@dataclass(frozen=True, slots=True)
class _OutputLocation:
    filename: str
    subfolder: str
    folder_type: str
    mime_type: ImageMimeType


class ComfyUIImageProvider:
    name: ImageProviderName = "comfyui"

    def __init__(
        self,
        *,
        base_url: str,
        workflow_path: Path | None,
        edit_workflow_path: Path | None = None,
        edit_face_workflow_path: Path | None = None,
        edit_lora_allowlist_path: Path | None = None,
        output_node_id: str | None = None,
        timeout_seconds: float = 30,
        max_result_bytes: int = 50 * 1024 * 1024,
        stalled_after_seconds: float = 90,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._workflow_path = workflow_path
        self._edit_workflow_path = edit_workflow_path
        self._edit_face_workflow_path = edit_face_workflow_path
        self._edit_lora_allowlist_path = edit_lora_allowlist_path
        self._output_node_id = output_node_id.strip() if output_node_id else None
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(5, timeout_seconds))
        self._max_result_bytes = max_result_bytes
        self._stalled_after_seconds = max(15, stalled_after_seconds)
        self._transport = transport
        self._jobs: dict[str, _TrackedComfyJob] = {}
        self._outputs: dict[str, _OutputLocation] = {}
        self._lock = RLock()
        self._listener_tasks: set[asyncio.Task[None]] = set()

    async def describe(self) -> ProviderDescriptor:
        try:
            self._load_workflow()
            response = await self._request("GET", "/system_stats")
            if not isinstance(response.json(), Mapping):
                raise ValueError("invalid system response")
        except (ImageProviderError, httpx.HTTPError, ValueError, json.JSONDecodeError):
            return ProviderDescriptor(
                "comfyui",
                "Local ComfyUI",
                False,
                "ComfyUI or its API workflow is not ready.",
            )
        return ProviderDescriptor(
            "comfyui",
            "Local ComfyUI",
            True,
            "Connected to the configured local generation workflow.",
        )

    async def describe_edit(self) -> ProviderDescriptor:
        try:
            if self._edit_workflow_path is None:
                raise self._workflow_missing_error()
            self._load_workflow(self._edit_workflow_path)
            response = await self._request("GET", "/system_stats")
            if not isinstance(response.json(), Mapping):
                raise ValueError("invalid system response")
        except (ImageProviderError, httpx.HTTPError, ValueError, json.JSONDecodeError):
            return ProviderDescriptor(
                "comfyui",
                "Local ComfyUI",
                False,
                "ComfyUI or its image edit workflow is not ready.",
            )
        return ProviderDescriptor(
            "comfyui",
            "Local ComfyUI",
            True,
            "Connected to the configured local image edit workflow.",
        )

    async def describe_edit_options(self) -> ImageEditProviderOptions:
        samplers: tuple[str, ...] = ("euler",)
        schedulers: tuple[str, ...] = ("simple",)
        try:
            response = await self._request("GET", "/object_info/KSampler")
            payload = response.json()
            node = payload.get("KSampler") if isinstance(payload, Mapping) else None
            inputs = node.get("input") if isinstance(node, Mapping) else None
            required = inputs.get("required") if isinstance(inputs, Mapping) else None
            samplers = self._option_values(required, "sampler_name") or samplers
            schedulers = self._option_values(required, "scheduler") or schedulers
        except (ImageProviderError, ValueError, json.JSONDecodeError):
            pass
        loras = tuple(LoraOption(item.id, item.label) for item in self._load_lora_allowlist())
        return ImageEditProviderOptions(
            samplers=samplers,
            schedulers=schedulers,
            loras=loras,
            default_sampler="euler" if "euler" in samplers else samplers[0],
            default_scheduler="simple" if "simple" in schedulers else schedulers[0],
        )

    async def describe_generation_options(self) -> ImageGenerationProviderOptions:
        samplers: tuple[str, ...] = ("euler",)
        schedulers: tuple[str, ...] = ("beta",)
        try:
            response = await self._request("GET", "/object_info/KSamplerAdvanced")
            payload = response.json()
            node = payload.get("KSamplerAdvanced") if isinstance(payload, Mapping) else None
            inputs = node.get("input") if isinstance(node, Mapping) else None
            required = inputs.get("required") if isinstance(inputs, Mapping) else None
            samplers = self._option_values(required, "sampler_name") or samplers
            schedulers = self._option_values(required, "scheduler") or schedulers
        except (ImageProviderError, ValueError, json.JSONDecodeError):
            pass
        loras = tuple(LoraOption(item.id, item.label) for item in self._load_lora_allowlist())
        return ImageGenerationProviderOptions(
            samplers=samplers,
            schedulers=schedulers,
            loras=loras,
            default_sampler="euler" if "euler" in samplers else samplers[0],
            default_scheduler="beta" if "beta" in schedulers else schedulers[0],
        )

    async def submit(self, request: ImageGenerationRequest) -> str:
        workflow = self._bind_workflow(self._load_workflow(), request)
        return await self._submit_workflow(request, workflow)

    async def submit_edit(
        self,
        request: ImageGenerationRequest,
        source: ProviderContent,
        face_reference: ProviderContent | None,
    ) -> str:
        source_name = await self._upload_image(request.job_id, "source", source)
        face_name = None
        workflow_path = self._edit_workflow_path
        if workflow_path is None:
            raise self._workflow_missing_error()
        if face_reference is not None:
            face_name = await self._upload_image(request.job_id, "face", face_reference)
            workflow_path = self._edit_face_workflow_path
            if workflow_path is None:
                raise ImageProviderError(
                    ProviderErrorDetails(
                        "face_workflow_missing",
                        "The optional face-reference workflow is not configured.",
                        "Configure the local face-reference template or remove the optional image.",
                        False,
                    )
                )
        workflow = self._bind_edit_workflow(
            self._load_workflow(workflow_path),
            request,
            source_name,
            face_name,
        )
        return await self._submit_workflow(request, workflow)

    async def _submit_workflow(
        self,
        request: ImageGenerationRequest,
        workflow: dict[str, Any],
    ) -> str:
        client_id = f"canvasrelay-{uuid4().hex}"
        if self._transport is None:
            ready = asyncio.Event()
            listener = asyncio.create_task(self._listen_for_progress(client_id, ready))
            self._listener_tasks.add(listener)
            listener.add_done_callback(self._listener_tasks.discard)
            with suppress(TimeoutError):
                await asyncio.wait_for(ready.wait(), timeout=1.5)
        try:
            response = await self._request(
                "POST",
                "/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            payload = response.json()
            provider_job_id = payload.get("prompt_id") if isinstance(payload, Mapping) else None
            if not isinstance(provider_job_id, str) or not provider_job_id:
                raise ValueError("missing prompt id")
        except ImageProviderError:
            raise
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            raise self._unavailable_error() from error
        with self._lock:
            self._jobs[provider_job_id] = _TrackedComfyJob(
                request,
                datetime.now(UTC),
                last_event_at=datetime.now(UTC),
            )
        return provider_job_id

    async def _upload_image(
        self,
        job_id: str,
        role: str,
        content: ProviderContent,
    ) -> str:
        extension = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }.get(content.mime_type)
        if extension is None:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "upload_type_invalid",
                    "The selected image format is not supported for editing.",
                    "Choose a PNG, JPEG, or WebP image.",
                    False,
                )
            )
        try:
            response = await self._request(
                "POST",
                "/upload/image",
                data={"type": "input", "subfolder": "canvasrelay", "overwrite": "false"},
                files={"image": (f"{job_id}_{role}{extension}", content.body, content.mime_type)},
            )
            payload = response.json()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            raise self._unavailable_error() from error
        name = payload.get("name") if isinstance(payload, Mapping) else None
        subfolder = payload.get("subfolder") if isinstance(payload, Mapping) else None
        if not isinstance(name, str) or not name:
            raise self._unavailable_error()
        return f"{subfolder}/{name}" if isinstance(subfolder, str) and subfolder else name

    def resume(self, provider_job_id: str, request: ImageGenerationRequest) -> None:
        with self._lock:
            self._jobs.setdefault(
                provider_job_id,
                _TrackedComfyJob(request, datetime.now(UTC)),
            )

    async def poll(self, provider_job_id: str) -> ProviderSnapshot:
        tracked = self._get_tracked(provider_job_id)
        try:
            history_response = await self._request("GET", f"/history/{provider_job_id}")
            history = history_response.json()
            entry = history.get(provider_job_id) if isinstance(history, Mapping) else None
            if isinstance(entry, Mapping):
                snapshot = self._snapshot_from_history(provider_job_id, tracked.request, entry)
                if snapshot is not None:
                    return self._remember_snapshot(provider_job_id, snapshot)

            queue_response = await self._request("GET", "/queue")
            queue = queue_response.json()
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            raise self._unavailable_error() from error

        if isinstance(queue, Mapping):
            if self._queue_contains(queue.get("queue_pending"), provider_job_id):
                return self._remember_snapshot(
                    provider_job_id,
                    ProviderSnapshot(
                        "queued",
                        0,
                        phase="queued",
                        progress_source="inferred",
                        progress_updated_at=datetime.now(UTC),
                    ),
                )
            if self._queue_contains(queue.get("queue_running"), provider_job_id):
                return self._running_snapshot(provider_job_id)

        grace_snapshot = self._snapshot_during_history_transition(provider_job_id)
        if grace_snapshot is not None:
            return grace_snapshot

        return ProviderSnapshot(
            "failed",
            None,
            phase="failed",
            error=ProviderErrorDetails(
                "provider_restarted",
                "The inference provider restarted before this job completed.",
                "Your settings were preserved. Retry the job when the provider is ready.",
                True,
            ),
        )

    def _remember_snapshot(
        self,
        provider_job_id: str,
        snapshot: ProviderSnapshot,
    ) -> ProviderSnapshot:
        with self._lock:
            tracked = self._jobs.get(provider_job_id)
            if tracked is not None:
                changed = (
                    tracked.phase != snapshot.phase
                    or tracked.current_step != snapshot.current_step
                    or tracked.total_steps != snapshot.total_steps
                )
                tracked.last_status = snapshot.status
                tracked.phase = snapshot.phase
                tracked.current_step = snapshot.current_step
                tracked.total_steps = snapshot.total_steps
                if changed and snapshot.progress_updated_at is not None:
                    tracked.last_event_at = snapshot.progress_updated_at
                tracked.missing_polls = 0
        return snapshot

    def _running_snapshot(self, provider_job_id: str) -> ProviderSnapshot:
        tracked = self._get_tracked(provider_job_id)
        phase: ImageProgressPhase = (
            tracked.phase if tracked.phase in {"preparing", "sampling", "saving"} else "preparing"
        )
        progress = self._step_progress(tracked.current_step, tracked.total_steps)
        return self._remember_snapshot(
            provider_job_id,
            ProviderSnapshot(
                "running",
                progress,
                phase=phase,
                current_step=tracked.current_step,
                total_steps=tracked.total_steps,
                progress_source="provider" if tracked.current_step is not None else "inferred",
                progress_updated_at=tracked.last_event_at,
                stalled=self._is_stalled("running", phase, tracked.last_event_at),
            ),
        )

    async def _listen_for_progress(self, client_id: str, ready: asyncio.Event) -> None:
        try:
            async with connect(
                self._websocket_url(client_id),
                max_size=1024 * 1024,
                ping_interval=20,
                open_timeout=min(5, self._timeout.connect or 5),
            ) as websocket:
                ready.set()
                async for message in websocket:
                    if isinstance(message, bytes):
                        continue
                    try:
                        payload = json.loads(message)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if self._apply_websocket_event(payload):
                        break
        except (OSError, TimeoutError, ValueError):
            ready.set()
        finally:
            ready.set()

    def _apply_websocket_event(self, payload: Any) -> bool:
        if not isinstance(payload, Mapping):
            return False
        event_type = payload.get("type")
        data = payload.get("data")
        if not isinstance(event_type, str) or not isinstance(data, Mapping):
            return False
        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str):
            return False
        now = datetime.now(UTC)
        with self._lock:
            tracked = self._jobs.get(prompt_id)
            if tracked is None:
                return False
            tracked.websocket_available = True
            tracked.last_event_at = now
            if event_type in {"execution_start", "executing"}:
                tracked.last_status = "running"
                if tracked.current_step is None:
                    tracked.phase = "preparing"
            elif event_type == "progress":
                current = data.get("value")
                total = data.get("max")
                if isinstance(current, int) and isinstance(total, int) and total > 0:
                    tracked.last_status = "running"
                    tracked.phase = "sampling"
                    tracked.current_step = max(0, min(current, total))
                    tracked.total_steps = total
            elif event_type == "execution_success":
                tracked.last_status = "running"
                tracked.phase = "saving"
                return True
            elif event_type in {"execution_error", "execution_interrupted"}:
                return True
        return False

    def _websocket_url(self, client_id: str) -> str:
        parts = urlsplit(self._base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        return urlunsplit((scheme, parts.netloc, "/ws", urlencode({"clientId": client_id}), ""))

    @staticmethod
    def _step_progress(current_step: int | None, total_steps: int | None) -> int | None:
        if current_step is None or total_steps is None or total_steps <= 0:
            return None
        return max(0, min(99, round(current_step / total_steps * 100)))

    def _is_stalled(
        self,
        status: ImageJobStatus,
        phase: ImageProgressPhase,
        last_event_at: datetime | None,
    ) -> bool:
        if status != "running" or phase not in {"preparing", "sampling"}:
            return False
        if last_event_at is None:
            return False
        return (datetime.now(UTC) - last_event_at).total_seconds() >= self._stalled_after_seconds

    def _snapshot_during_history_transition(
        self,
        provider_job_id: str,
    ) -> ProviderSnapshot | None:
        with self._lock:
            tracked = self._jobs.get(provider_job_id)
            if tracked is None:
                return None
            tracked.missing_polls += 1
            if tracked.missing_polls > 5:
                return None
            status: ImageJobStatus = (
                tracked.last_status
                if tracked.last_status in {"queued", "running"}
                else "running"
            )
            phase = tracked.phase if status == "running" else "queued"
            current_step = tracked.current_step
            total_steps = tracked.total_steps
            last_event_at = tracked.last_event_at
        return ProviderSnapshot(
            status,
            0 if status == "queued" else self._step_progress(current_step, total_steps),
            phase=phase,
            current_step=current_step,
            total_steps=total_steps,
            progress_source="provider" if current_step is not None else "inferred",
            progress_updated_at=last_event_at,
            stalled=self._is_stalled(status, phase, last_event_at),
        )

    async def cancel(self, provider_job_id: str) -> ProviderSnapshot:
        self._get_tracked(provider_job_id)
        try:
            queue_response = await self._request("GET", "/queue")
            queue = queue_response.json()
            is_running = isinstance(queue, Mapping) and self._queue_contains(
                queue.get("queue_running"), provider_job_id
            )
            is_pending = isinstance(queue, Mapping) and self._queue_contains(
                queue.get("queue_pending"), provider_job_id
            )
            if is_running:
                await self._request("POST", "/interrupt", json={})
            elif is_pending:
                await self._request("POST", "/queue", json={"delete": [provider_job_id]})
            else:
                return await self.poll(provider_job_id)
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            raise self._unavailable_error() from error
        return ProviderSnapshot("canceled", 0, phase="canceled", progress_source="inferred")

    async def collect(self, provider_job_id: str) -> ProviderContent:
        self._get_tracked(provider_job_id)
        with self._lock:
            output = self._outputs.get(provider_job_id)
        if output is None:
            snapshot = await self.poll(provider_job_id)
            if snapshot.status != "completed":
                raise ImageProviderError(
                    ProviderErrorDetails(
                        "result_not_ready",
                        "The ComfyUI result is not ready yet.",
                        "Wait for generation to complete and try again.",
                        True,
                    )
                )
            with self._lock:
                output = self._outputs.get(provider_job_id)
        if output is None:
            raise self._output_error()

        try:
            response = await self._request(
                "GET",
                "/view",
                params={
                    "filename": output.filename,
                    "subfolder": output.subfolder,
                    "type": output.folder_type,
                },
            )
        except httpx.HTTPError as error:
            raise self._unavailable_error() from error
        if len(response.content) > self._max_result_bytes:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "result_too_large",
                    "The generated image is too large to preview.",
                    "Reduce the workflow output dimensions and try again.",
                    False,
                )
            )
        return ProviderContent(response.content, output.mime_type)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response
        except httpx.HTTPError as error:
            raise self._unavailable_error() from error

    def _load_workflow(self, workflow_path: Path | None = None) -> dict[str, Any]:
        path = workflow_path if workflow_path is not None else self._workflow_path
        if path is None or not path.is_file():
            raise ImageProviderError(
                ProviderErrorDetails(
                    "workflow_missing",
                    "The ComfyUI API workflow is not configured.",
                    "Set the server workflow path to an API-format JSON template.",
                    False,
                )
            )
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("workflow is too large")
            workflow = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "workflow_invalid",
                    "The ComfyUI workflow template is invalid.",
                    "Export the workflow in API format and check its placeholders.",
                    False,
                )
            ) from error
        if not isinstance(workflow, dict) or not workflow:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "workflow_invalid",
                    "The ComfyUI workflow template is invalid.",
                    "Export the workflow in API format and check its placeholders.",
                    False,
                )
            )
        for node in workflow.values():
            if not isinstance(node, dict) or not isinstance(node.get("class_type"), str):
                raise ImageProviderError(
                    ProviderErrorDetails(
                        "workflow_invalid",
                        "The ComfyUI workflow is not in API format.",
                        "Use ComfyUI's API-format export and try again.",
                        False,
                    )
                )
        return workflow

    @staticmethod
    def _workflow_missing_error() -> ImageProviderError:
        return ImageProviderError(
            ProviderErrorDetails(
                "workflow_missing",
                "The ComfyUI API workflow is not configured.",
                "Set the server workflow path to an API-format JSON template.",
                False,
            )
        )

    def _bind_workflow(
        self,
        workflow: dict[str, Any],
        request: ImageGenerationRequest,
    ) -> dict[str, Any]:
        width, height = image_dimensions(request.aspect_ratio)
        replacements: dict[str, str | int] = {
            "{{prompt}}": request.prompt,
            "{{seed}}": request.seed,
            "{{width}}": width,
            "{{height}}": height,
            "{{filename_prefix}}": f"canvasrelay/{request.job_id}",
        }
        seen: set[str] = set()

        def replace_value(value: Any) -> Any:
            if isinstance(value, str) and value in replacements:
                seen.add(value)
                return replacements[value]
            if isinstance(value, list):
                return [replace_value(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_value(item) for key, item in value.items()}
            return value

        bound = replace_value(deepcopy(workflow))
        if not isinstance(bound, dict):
            raise ImageProviderError(
                ProviderErrorDetails(
                    "workflow_invalid",
                    "The ComfyUI workflow is not a JSON object.",
                    "Export the workflow in ComfyUI API format and try again.",
                    False,
                )
            )
        required = PLACEHOLDERS - {"{{filename_prefix}}"}
        if not required.issubset(seen):
            raise ImageProviderError(
                ProviderErrorDetails(
                    "workflow_bindings_missing",
                    "The ComfyUI workflow is missing required CanvasRelay placeholders.",
                    "Add prompt, seed, width, and height placeholders to the API workflow.",
                    False,
                )
            )
        typed_bound = cast(dict[str, Any], bound)
        self._apply_generation_controls(typed_bound, request)
        settings = request.generation_settings
        if settings is not None:
            self._apply_lora_chain(typed_bound, settings.loras)
        return typed_bound

    def _bind_edit_workflow(
        self,
        workflow: dict[str, Any],
        request: ImageGenerationRequest,
        source_image: str,
        face_image: str | None,
    ) -> dict[str, Any]:
        width, height = image_dimensions(request.aspect_ratio)
        replacements: dict[str, str | int | float] = {
            "{{prompt}}": request.prompt,
            "{{seed}}": request.seed,
            "{{width}}": width,
            "{{height}}": height,
            "{{filename_prefix}}": f"canvasrelay/{request.job_id}",
            "{{source_image}}": source_image,
        }
        if request.edit_settings is not None:
            replacements.update(
                {
                    "{{edit_reference_influence}}": request.edit_settings.reference_influence,
                    "{{edit_grounding_resolution}}": request.edit_settings.grounding_resolution,
                    "{{edit_fit_mode}}": (
                        "fit" if request.edit_settings.fit_mode == "fit" else "crop (legacy)"
                    ),
                }
            )
        if face_image is not None:
            replacements["{{face_image}}"] = face_image
        seen: set[str] = set()

        def replace_value(value: Any) -> Any:
            if isinstance(value, str) and value in replacements:
                seen.add(value)
                return replacements[value]
            if isinstance(value, list):
                return [replace_value(item) for item in value]
            if isinstance(value, dict):
                return {key: replace_value(item) for key, item in value.items()}
            return value

        bound = replace_value(deepcopy(workflow))
        required = EDIT_PLACEHOLDERS - {"{{filename_prefix}}"}
        if face_image is not None:
            required.add("{{face_image}}")
        if not isinstance(bound, dict) or not required.issubset(seen):
            raise ImageProviderError(
                ProviderErrorDetails(
                    "workflow_bindings_missing",
                    "The ComfyUI image edit workflow is missing required placeholders.",
                    "Add source, prompt, seed, width, and height bindings to the local template.",
                    False,
                )
            )
        typed_bound = cast(dict[str, Any], bound)
        self._apply_edit_controls(typed_bound, request)
        settings = request.edit_settings
        if settings is not None:
            self._apply_lora_chain(typed_bound, settings.loras)
        return typed_bound

    def _apply_generation_controls(
        self,
        workflow: dict[str, Any],
        request: ImageGenerationRequest,
    ) -> None:
        settings = request.generation_settings
        if settings is None:
            return
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            if class_type in {"KSampler", "KSamplerAdvanced"}:
                inputs.update(
                    {
                        "steps": settings.steps,
                        "cfg": settings.cfg,
                        "sampler_name": settings.sampler,
                        "scheduler": settings.scheduler,
                    }
                )
            if class_type == "ModelSamplingAuraFlow":
                inputs["shift"] = settings.shift

    def _apply_edit_controls(
        self,
        workflow: dict[str, Any],
        request: ImageGenerationRequest,
    ) -> None:
        settings = request.edit_settings
        if settings is None:
            return
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            if class_type == "KSampler":
                inputs.update(
                    {
                        "steps": settings.steps,
                        "cfg": settings.cfg,
                        "sampler_name": settings.sampler,
                        "scheduler": settings.scheduler,
                    }
                )

    def _apply_lora_chain(
        self,
        workflow: dict[str, Any],
        selections: tuple[LoraSelection, ...],
    ) -> None:
        if not selections:
            return
        allowlist = {item.id: item for item in self._load_lora_allowlist()}
        selected = []
        for selection in selections:
            entry = allowlist.get(selection.id)
            if entry is None:
                raise self._unsupported_options_error()
            selected.append((entry, selection))

        sampler_inputs = [
            inputs
            for node in workflow.values()
            if isinstance(node, dict)
            and node.get("class_type") in {"KSampler", "KSamplerAdvanced"}
            and isinstance((inputs := node.get("inputs")), dict)
            and self._is_node_link(inputs.get("model"))
        ]
        clip_inputs = [
            inputs
            for node in workflow.values()
            if isinstance(node, dict)
            and node.get("class_type") not in {"LoraLoader", "LoraLoaderModelOnly"}
            and isinstance((inputs := node.get("inputs")), dict)
            and self._is_node_link(inputs.get("clip"))
        ]
        model_links = {tuple(cast(list[Any], inputs["model"])) for inputs in sampler_inputs}
        clip_links = {tuple(cast(list[Any], inputs["clip"])) for inputs in clip_inputs}
        if len(model_links) != 1 or len(clip_links) != 1:
            raise self._unsupported_options_error()
        model_link: list[Any] = list(next(iter(model_links)))
        clip_link: list[Any] = list(next(iter(clip_links)))

        existing_names = {
            inputs.get("lora_name")
            for node in workflow.values()
            if isinstance(node, dict)
            and isinstance((inputs := node.get("inputs")), dict)
            and node.get("class_type") in {"LoraLoader", "LoraLoaderModelOnly"}
        }
        for index, (entry, selection) in enumerate(selected, start=1):
            if entry.filename in existing_names:
                continue
            node_id = self._available_node_id(workflow, f"cr_lora_{index:03d}")
            workflow[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": model_link,
                    "clip": clip_link,
                    "lora_name": entry.filename,
                    "strength_model": selection.model_weight,
                    "strength_clip": selection.clip_weight,
                },
                "_meta": {"title": "CanvasRelay allowed LoRA"},
            }
            model_link = [node_id, 0]
            clip_link = [node_id, 1]

        for inputs in sampler_inputs:
            inputs["model"] = model_link
        for inputs in clip_inputs:
            inputs["clip"] = clip_link

    def _snapshot_from_history(
        self,
        provider_job_id: str,
        request: ImageGenerationRequest,
        entry: Mapping[str, Any],
    ) -> ProviderSnapshot | None:
        status = entry.get("status")
        status_text = status.get("status_str") if isinstance(status, Mapping) else None
        if status_text == "error" or self._history_has_error(status):
            return ProviderSnapshot(
                "failed",
                None,
                phase="failed",
                error=ProviderErrorDetails(
                    "provider_execution_failed",
                    "ComfyUI could not execute the configured workflow.",
                    "Check the workflow nodes and model availability in ComfyUI.",
                    True,
                ),
            )
        completed = status.get("completed") if isinstance(status, Mapping) else None
        if completed is not True:
            return None
        output = self._select_output(entry.get("outputs"))
        if output is None:
            return ProviderSnapshot(
                "failed", None, error=self._output_error().details, phase="failed"
            )
        with self._lock:
            self._outputs[provider_job_id] = output
        width, height = image_dimensions(request.aspect_ratio)
        settings = request.generation_settings or request.edit_settings
        total_steps = settings.steps if settings is not None else None
        return ProviderSnapshot(
            "completed",
            100,
            ProviderResult(output.mime_type, width, height),
            phase="completed",
            current_step=total_steps,
            total_steps=total_steps,
            progress_source="provider",
            progress_updated_at=datetime.now(UTC),
        )

    def _select_output(self, outputs: Any) -> _OutputLocation | None:
        if not isinstance(outputs, Mapping):
            return None
        node_ids = (
            [self._output_node_id]
            if self._output_node_id
            else sorted(outputs, key=_node_sort_key)
        )
        for node_id in node_ids:
            node_output = outputs.get(node_id) if node_id is not None else None
            if not isinstance(node_output, Mapping):
                continue
            images = node_output.get("images")
            if not isinstance(images, list):
                continue
            for image in images:
                if not isinstance(image, Mapping):
                    continue
                filename = image.get("filename")
                if not isinstance(filename, str) or not filename:
                    continue
                mime_type = _mime_type_for(filename)
                if mime_type is None:
                    continue
                subfolder = image.get("subfolder")
                folder_type = image.get("type")
                return _OutputLocation(
                    filename=filename,
                    subfolder=subfolder if isinstance(subfolder, str) else "",
                    folder_type=folder_type if isinstance(folder_type, str) else "output",
                    mime_type=mime_type,
                )
        return None

    @staticmethod
    def _history_has_error(status: Any) -> bool:
        if not isinstance(status, Mapping):
            return False
        messages = status.get("messages")
        return isinstance(messages, list) and any(
            isinstance(message, list) and message and message[0] == "execution_error"
            for message in messages
        )

    @staticmethod
    def _queue_contains(queue: Any, provider_job_id: str) -> bool:
        if not isinstance(queue, list):
            return False
        return any(
            isinstance(item, list) and len(item) > 1 and item[1] == provider_job_id
            for item in queue
        )

    @staticmethod
    def _option_values(required: Any, name: str) -> tuple[str, ...]:
        if not isinstance(required, Mapping):
            return ()
        definition = required.get(name)
        if not isinstance(definition, list) or not definition:
            return ()
        values = definition[0]
        if not isinstance(values, list):
            return ()
        return tuple(value for value in values if isinstance(value, str) and value)

    def _load_lora_allowlist(self) -> tuple[_LoraAllowlistEntry, ...]:
        path = self._edit_lora_allowlist_path
        if path is None or not path.is_file():
            return ()
        try:
            if path.stat().st_size > 128 * 1024:
                return ()
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return ()
        items = payload.get("loras") if isinstance(payload, Mapping) else None
        if not isinstance(items, list):
            return ()
        entries: list[_LoraAllowlistEntry] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, Mapping):
                continue
            identifier = item.get("id")
            label = item.get("label")
            filename = item.get("filename")
            if (
                not isinstance(identifier, str)
                or not identifier.replace("-", "").replace("_", "").isalnum()
                or identifier in seen
                or not isinstance(label, str)
                or not label.strip()
                or not isinstance(filename, str)
                or not filename.strip()
                or Path(filename).is_absolute()
            ):
                continue
            seen.add(identifier)
            entries.append(_LoraAllowlistEntry(identifier, label.strip(), filename.strip()))
        return tuple(entries)

    @staticmethod
    def _is_node_link(value: Any) -> bool:
        return (
            isinstance(value, list)
            and len(value) == 2
            and isinstance(value[0], str)
            and isinstance(value[1], int)
        )

    @staticmethod
    def _available_node_id(workflow: Mapping[str, Any], preferred: str) -> str:
        if preferred not in workflow:
            return preferred
        index = 2
        while f"{preferred}_{index}" in workflow:
            index += 1
        return f"{preferred}_{index}"

    @staticmethod
    def _unsupported_options_error() -> ImageProviderError:
        return ImageProviderError(
            ProviderErrorDetails(
                "edit_options_invalid",
                "The selected edit controls are not supported by this local workflow.",
                "Refresh the edit options and choose available settings.",
                False,
            )
        )

    def _get_tracked(self, provider_job_id: str) -> _TrackedComfyJob:
        with self._lock:
            tracked = self._jobs.get(provider_job_id)
        if tracked is None:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "provider_job_missing",
                    "The ComfyUI job is no longer available to this server process.",
                    "Create a new image job.",
                    False,
                )
            )
        return tracked

    @staticmethod
    def _unavailable_error() -> ImageProviderError:
        return ImageProviderError(
            ProviderErrorDetails(
                "provider_unavailable",
                "The local ComfyUI provider is unavailable.",
                "Start ComfyUI, verify the workflow configuration, and retry.",
                True,
            )
        )

    @staticmethod
    def _output_error() -> ImageProviderError:
        return ImageProviderError(
            ProviderErrorDetails(
                "provider_output_missing",
                "ComfyUI completed without a supported image output.",
                "Check the configured Save Image output node and retry.",
                True,
            )
        )


def _mime_type_for(filename: str) -> ImageMimeType | None:
    suffix = Path(filename).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix)  # type: ignore[return-value]


def _node_sort_key(node_id: object) -> tuple[int, str]:
    text = str(node_id)
    return (int(text), text) if text.isdigit() else (2**31 - 1, text)
