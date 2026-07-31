from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, cast

import httpx

from app.domain.image_jobs import (
    ImageGenerationRequest,
    ImageJobStatus,
    ImageMimeType,
    ImageProviderName,
    ProviderContent,
    ProviderErrorDetails,
    ProviderResult,
    ProviderSnapshot,
    image_dimensions,
)
from app.providers.base import ImageProviderError, ProviderDescriptor

PLACEHOLDERS = {
    "{{prompt}}",
    "{{seed}}",
    "{{width}}",
    "{{height}}",
    "{{filename_prefix}}",
}


@dataclass(slots=True)
class _TrackedComfyJob:
    request: ImageGenerationRequest
    submitted_at: datetime
    last_status: ImageJobStatus = "queued"
    missing_polls: int = 0


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
        output_node_id: str | None = None,
        timeout_seconds: float = 30,
        max_result_bytes: int = 50 * 1024 * 1024,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._workflow_path = workflow_path
        self._output_node_id = output_node_id.strip() if output_node_id else None
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(5, timeout_seconds))
        self._max_result_bytes = max_result_bytes
        self._transport = transport
        self._jobs: dict[str, _TrackedComfyJob] = {}
        self._outputs: dict[str, _OutputLocation] = {}
        self._lock = RLock()

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

    async def submit(self, request: ImageGenerationRequest) -> str:
        workflow = self._bind_workflow(self._load_workflow(), request)
        try:
            response = await self._request(
                "POST",
                "/prompt",
                json={"prompt": workflow, "client_id": "canvasrelay"},
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
            self._jobs[provider_job_id] = _TrackedComfyJob(request, datetime.now(UTC))
        return provider_job_id

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
                    ProviderSnapshot("queued", 0),
                )
            if self._queue_contains(queue.get("queue_running"), provider_job_id):
                return self._remember_snapshot(
                    provider_job_id,
                    ProviderSnapshot("running", None),
                )

        grace_snapshot = self._snapshot_during_history_transition(provider_job_id)
        if grace_snapshot is not None:
            return grace_snapshot

        return ProviderSnapshot(
            "failed",
            None,
            error=ProviderErrorDetails(
                "provider_job_missing",
                "ComfyUI no longer reports this generation job.",
                "Check the ComfyUI queue and create a new job.",
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
                tracked.last_status = snapshot.status
                tracked.missing_polls = 0
        return snapshot

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
        return ProviderSnapshot(status, 0 if status == "queued" else None)

    async def cancel(self, provider_job_id: str) -> ProviderSnapshot:
        self._get_tracked(provider_job_id)
        try:
            queue_response = await self._request("GET", "/queue")
            queue = queue_response.json()
            if isinstance(queue, Mapping) and self._queue_contains(
                queue.get("queue_running"), provider_job_id
            ):
                await self._request("POST", "/interrupt", json={})
            else:
                await self._request("POST", "/queue", json={"delete": [provider_job_id]})
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            raise self._unavailable_error() from error
        return ProviderSnapshot("canceled", 0)

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

    def _load_workflow(self) -> dict[str, Any]:
        path = self._workflow_path
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
        return cast(dict[str, Any], bound)

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
            return ProviderSnapshot("failed", None, error=self._output_error().details)
        with self._lock:
            self._outputs[provider_job_id] = output
        width, height = image_dimensions(request.aspect_ratio)
        return ProviderSnapshot("completed", 100, ProviderResult(output.mime_type, width, height))

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
