import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.domain.image_jobs import (
    ImageEditSettings,
    ImageGenerationRequest,
    LoraSelection,
    ProviderContent,
)
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


def write_edit_workflow(path: Path, *, include_face: bool) -> None:
    inputs: dict[str, Any] = {
        "prompt": "{{prompt}}",
        "seed": "{{seed}}",
        "width": "{{width}}",
        "height": "{{height}}",
        "source": "{{source_image}}",
    }
    if include_face:
        inputs["face"] = "{{face_image}}"
    path.write_text(
        json.dumps(
            {
                "1": {"class_type": "EditNode", "inputs": inputs},
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
async def test_comfyui_uploads_optional_face_and_selects_face_edit_workflow(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "workflow.json"
    edit_path = tmp_path / "edit.json"
    face_path = tmp_path / "edit-face.json"
    write_workflow(workflow_path)
    write_edit_workflow(edit_path, include_face=False)
    write_edit_workflow(face_path, include_face=True)
    submitted: dict[str, Any] = {}
    uploaded: list[bytes] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/upload/image":
            uploaded.append(http_request.content)
            return httpx.Response(
                200,
                json={
                    "name": f"upload_{len(uploaded)}.png",
                    "subfolder": "canvasrelay",
                },
            )
        if http_request.url.path == "/prompt":
            submitted.update(json.loads(http_request.content))
            return httpx.Response(200, json={"prompt_id": "provider_edit"})
        raise AssertionError(
            f"Unexpected request: {http_request.method} {http_request.url.path}"
        )

    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        edit_workflow_path=edit_path,
        edit_face_workflow_path=face_path,
        transport=httpx.MockTransport(handler),
    )

    provider_job_id = await provider.submit_edit(
        request(),
        ProviderContent(b"source-image", "image/png"),
        ProviderContent(b"face-image", "image/png"),
    )

    assert provider_job_id == "provider_edit"
    assert len(uploaded) == 2
    assert submitted["prompt"]["1"]["inputs"] == {
        "prompt": "A calm studio product photograph",
        "seed": 47,
        "width": 1152,
        "height": 864,
        "source": "canvasrelay/upload_1.png",
        "face": "canvasrelay/upload_2.png",
    }


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
async def test_comfyui_tolerates_queue_to_history_transition(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.json"
    write_workflow(workflow_path)
    phase = "running"

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal phase
        if http_request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "provider_transition"})
        if http_request.url.path == "/history/provider_transition":
            if phase != "completed":
                return httpx.Response(200, json={})
            return httpx.Response(
                200,
                json={
                    "provider_transition": {
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
        if http_request.url.path == "/queue":
            if phase == "running":
                return httpx.Response(
                    200,
                    json={"queue_running": [[1, "provider_transition", {}, {}, []]]},
                )
            return httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        raise AssertionError(f"Unexpected request: {http_request.method} {http_request.url.path}")

    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        transport=httpx.MockTransport(handler),
    )
    provider_id = await provider.submit(request())

    running = await provider.poll(provider_id)
    phase = "transition"
    transitioning = await provider.poll(provider_id)
    phase = "completed"
    completed = await provider.poll(provider_id)

    assert running.status == "running"
    assert transitioning.status == "running" and transitioning.error is None
    assert completed.status == "completed"


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


@pytest.mark.anyio
async def test_comfyui_applies_supported_controls_and_ordered_lora_chain(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "workflow.json"
    edit_path = tmp_path / "edit.json"
    allowlist_path = tmp_path / "allowlist.json"
    write_workflow(workflow_path)
    edit_path.write_text(
        json.dumps(
            {
                "1": {"class_type": "LoadImage", "inputs": {"image": "{{source_image}}"}},
                "2": {"class_type": "BaseModel", "inputs": {}},
                "3": {"class_type": "BaseClip", "inputs": {}},
                "4": {
                    "class_type": "EditModelPatch",
                    "inputs": {
                        "model": ["2", 0],
                        "reference": "{{edit_reference_influence}}",
                        "fit": "{{edit_fit_mode}}",
                    },
                },
                "5": {
                    "class_type": "EditTextEncode",
                    "inputs": {
                        "clip": ["3", 0],
                        "grounding": "{{edit_grounding_resolution}}",
                    },
                },
                "6": {
                    "class_type": "KSampler",
                    "inputs": {
                        "model": ["4", 0], "steps": 4, "cfg": 1,
                        "sampler_name": "euler", "scheduler": "simple",
                        "prompt": "{{prompt}}", "seed": "{{seed}}",
                        "width": "{{width}}", "height": "{{height}}",
                    },
                },
                "9": {
                    "class_type": "SaveImage",
                    "inputs": {"filename_prefix": "{{filename_prefix}}"},
                },
            }
        ),
        encoding="utf-8",
    )
    allowlist_path.write_text(
        json.dumps(
            {
                "loras": [
                    {"id": "detail", "label": "Detail", "filename": "local/detail.safetensors"},
                    {"id": "light", "label": "Light", "filename": "local/light.safetensors"},
                ]
            }
        ),
        encoding="utf-8",
    )
    submitted: dict[str, Any] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/object_info/KSampler":
            return httpx.Response(200, json={"KSampler": {"input": {"required": {
                "sampler_name": [["euler", "dpmpp_2m"]],
                "scheduler": [["simple", "karras"]],
            }}}})
        if http_request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": "source.png", "subfolder": "canvasrelay"})
        if http_request.url.path == "/prompt":
            submitted.update(json.loads(http_request.content))
            return httpx.Response(200, json={"prompt_id": "advanced_edit"})
        raise AssertionError(f"Unexpected request: {http_request.method} {http_request.url.path}")

    base = request()
    edit_request = ImageGenerationRequest(
        job_id=base.job_id,
        prompt=base.prompt,
        aspect_ratio=base.aspect_ratio,
        style=base.style,
        seed=base.seed,
        created_at=base.created_at,
        edit_settings=ImageEditSettings(
            steps=12,
            cfg=1.7,
            reference_influence=5.5,
            grounding_resolution=1024,
            fit_mode="crop",
            sampler="dpmpp_2m",
            scheduler="karras",
            loras=(LoraSelection("detail", 0.7, 0.3), LoraSelection("light", 0.4, 0.2)),
        ),
    )
    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        edit_workflow_path=edit_path,
        edit_lora_allowlist_path=allowlist_path,
        transport=httpx.MockTransport(handler),
    )

    options = await provider.describe_edit_options()
    await provider.submit_edit(edit_request, ProviderContent(b"source", "image/png"), None)
    workflow = submitted["prompt"]

    assert options.samplers == ("euler", "dpmpp_2m")
    assert [item.id for item in options.loras] == ["detail", "light"]
    assert workflow["6"]["inputs"]["steps"] == 12
    assert workflow["6"]["inputs"]["sampler_name"] == "dpmpp_2m"
    assert workflow["4"]["inputs"]["reference"] == 5.5
    assert workflow["4"]["inputs"]["fit"] == "crop (legacy)"
    assert workflow["5"]["inputs"]["grounding"] == 1024
    assert workflow["6"]["inputs"]["model"] == ["cr_lora_002", 0]
    assert workflow["5"]["inputs"]["clip"] == ["cr_lora_002", 1]
    assert workflow["cr_lora_001"]["inputs"]["strength_model"] == 0.7
    assert workflow["cr_lora_002"]["inputs"]["clip"] == ["cr_lora_001", 1]


@pytest.mark.anyio
async def test_comfyui_does_not_interrupt_an_unrelated_running_prompt(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.json"
    write_workflow(workflow_path)
    mutations: list[str] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "ours"})
        if http_request.url.path == "/history/ours":
            return httpx.Response(200, json={})
        if http_request.url.path == "/queue" and http_request.method == "GET":
            return httpx.Response(
                200,
                json={"queue_running": [[1, "someone-else", {}, {}, []]], "queue_pending": []},
            )
        if http_request.method == "POST":
            mutations.append(http_request.url.path)
            return httpx.Response(200, json={})
        raise AssertionError(f"Unexpected request: {http_request.method} {http_request.url.path}")

    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        transport=httpx.MockTransport(handler),
    )
    provider_id = await provider.submit(request())

    snapshot = await provider.cancel(provider_id)

    assert snapshot.status == "queued"
    assert mutations == []


@pytest.mark.anyio
async def test_websocket_steps_override_polling_and_report_a_stall(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.json"
    write_workflow(workflow_path)

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/history/ws_job":
            return httpx.Response(200, json={})
        if http_request.url.path == "/queue":
            return httpx.Response(200, json={"queue_running": [[1, "ws_job", {}, {}, []]]})
        raise AssertionError(f"Unexpected request: {http_request.method} {http_request.url.path}")

    provider = ComfyUIImageProvider(
        base_url="http://comfy.test",
        workflow_path=workflow_path,
        stalled_after_seconds=15,
        transport=httpx.MockTransport(handler),
    )
    provider.resume("ws_job", request())
    provider._apply_websocket_event(
        {"type": "progress", "data": {"prompt_id": "ws_job", "value": 3, "max": 8}}
    )

    progressing = await provider.poll("ws_job")
    provider._jobs["ws_job"].last_event_at = datetime.now(UTC) - timedelta(seconds=20)
    stalled = await provider.poll("ws_job")

    assert progressing.phase == "sampling"
    assert progressing.current_step == 3 and progressing.total_steps == 8
    assert progressing.progress == 38
    assert stalled.stalled is True
