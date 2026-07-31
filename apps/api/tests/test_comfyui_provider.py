import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.domain.image_jobs import ImageGenerationRequest
from app.providers.comfyui import ComfyUIImageProvider


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def write_workflow(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "1": {
                    "class_type": "PromptNode",
                    "inputs": {"text": "{{prompt}}", "seed": "{{seed}}"},
                },
                "2": {
                    "class_type": "SizeNode",
                    "inputs": {"width": "{{width}}", "height": "{{height}}"},
                },
                "9": {
                    "class_type": "SaveImage",
                    "inputs": {"filename_prefix": "{{filename_prefix}}"},
                },
            }
        ),
        encoding="utf-8",
    )


def request() -> ImageGenerationRequest:
    from datetime import UTC, datetime

    return ImageGenerationRequest(
        job_id="img_test",
        prompt="A calm studio product photograph",
        aspect_ratio="4:3",
        style="product",
        seed=47,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_comfyui_submits_bound_api_workflow_and_collects_output(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.json"
    write_workflow(workflow_path)
    submitted: dict[str, Any] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {"comfyui_version": "test"}})
        if http_request.url.path == "/prompt":
            submitted.update(json.loads(http_request.content))
            return httpx.Response(200, json={"prompt_id": "provider_1", "node_errors": {}})
        if http_request.url.path == "/history/provider_1":
            return httpx.Response(
                200,
                json={
                    "provider_1": {
                        "status": {"status_str": "success", "completed": True},
                        "outputs": {
                            "9": {
                                "images": [
                                    {"filename": "result.png", "subfolder": "", "type": "output"}
                                ]
                            }
                        },
                    }
                },
            )
        if http_request.url.path == "/view":
            return httpx.Response(200, content=b"safe-png-content")
        raise AssertionError(f"Unexpected request: {http_request.method} {http_request.url.path}")

    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        transport=httpx.MockTransport(handler),
    )

    descriptor = await provider.describe()
    provider_id = await provider.submit(request())
    snapshot = await provider.poll(provider_id)
    content = await provider.collect(provider_id)

    assert descriptor.ready is True
    assert submitted["prompt"]["1"]["inputs"] == {
        "text": "A calm studio product photograph",
        "seed": 47,
    }
    assert submitted["prompt"]["2"]["inputs"] == {"width": 1152, "height": 864}
    assert snapshot.status == "completed"
    assert snapshot.result is not None and snapshot.result.mime_type == "image/png"
    assert content.body == b"safe-png-content"


@pytest.mark.anyio
async def test_comfyui_reports_queue_without_inventing_running_progress(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.json"
    write_workflow(workflow_path)
    state = "pending"

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal state
        if http_request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "provider_2"})
        if http_request.url.path == "/history/provider_2":
            return httpx.Response(200, json={})
        if http_request.url.path == "/queue" and http_request.method == "GET":
            key = "queue_pending" if state == "pending" else "queue_running"
            return httpx.Response(200, json={key: [[1, "provider_2", {}, {}, []]]})
        raise AssertionError(f"Unexpected request: {http_request.method} {http_request.url.path}")

    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        transport=httpx.MockTransport(handler),
    )
    provider_id = await provider.submit(request())

    queued = await provider.poll(provider_id)
    state = "running"
    running = await provider.poll(provider_id)

    assert queued.status == "queued" and queued.progress == 0
    assert running.status == "running" and running.progress is None


@pytest.mark.anyio
async def test_comfyui_normalizes_execution_errors(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.json"
    write_workflow(workflow_path)

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "provider_3"})
        if http_request.url.path == "/history/provider_3":
            return httpx.Response(
                200,
                json={
                    "provider_3": {
                        "status": {
                            "status_str": "error",
                            "completed": False,
                            "messages": [["execution_error", {"private": "raw detail"}]],
                        },
                        "outputs": {},
                    }
                },
            )
        raise AssertionError(f"Unexpected request: {http_request.method} {http_request.url.path}")

    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        transport=httpx.MockTransport(handler),
    )
    snapshot = await provider.poll(await provider.submit(request()))

    assert snapshot.status == "failed"
    assert snapshot.error is not None
    assert snapshot.error.code == "provider_execution_failed"
    assert "raw detail" not in snapshot.error.message
