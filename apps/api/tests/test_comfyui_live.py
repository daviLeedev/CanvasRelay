from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import cast

import httpx
import pytest

LIVE_API_URL = os.getenv("CANVASRELAY_LIVE_TEST_API_URL", "").rstrip("/")
LIVE_TIMEOUT_SECONDS = float(os.getenv("CANVASRELAY_LIVE_TEST_TIMEOUT_SECONDS", "600"))

pytestmark = [
    pytest.mark.live_comfyui,
    pytest.mark.skipif(
        not LIVE_API_URL,
        reason="Set CANVASRELAY_LIVE_TEST_API_URL to run local ComfyUI integration tests.",
    ),
]


def _wait_for_terminal(client: httpx.Client, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + LIVE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/image-jobs/{job_id}")
        response.raise_for_status()
        payload = cast(dict[str, object], response.json())
        status = payload.get("status")
        if status == "completed":
            return payload
        if status in {"failed", "canceled"}:
            pytest.fail(f"Live image job reached terminal status {status!r}.")
        time.sleep(1)
    pytest.fail("Live image job did not complete before the integration timeout.")


@pytest.fixture(scope="module")
def live_client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=LIVE_API_URL, timeout=30) as client:
        health = client.get("/api/v1/health")
        health.raise_for_status()
        provider = client.get("/api/v1/providers/image")
        provider.raise_for_status()
        assert provider.json()["provider"] == "comfyui"
        assert provider.json()["ready"] is True
        yield client


@pytest.fixture(scope="module")
def completed_generation(live_client: httpx.Client) -> tuple[dict[str, object], bytes, str]:
    response = live_client.post(
        "/api/v1/image-jobs",
        json={
            "prompt": "A ceramic desk lamp in a quiet daylight studio, clean product photograph",
            "aspectRatio": "4:3",
            "style": "product",
            "seed": 260801,
        },
    )
    response.raise_for_status()
    job = _wait_for_terminal(live_client, cast(str, response.json()["id"]))
    result_url = cast(str, cast(dict[str, object], job["result"])["url"])
    result = live_client.get(result_url)
    result.raise_for_status()
    return job, result.content, result.headers["content-type"].split(";", 1)[0]


def test_live_generation_is_owned_by_canvasrelay_after_completion(
    live_client: httpx.Client,
    completed_generation: tuple[dict[str, object], bytes, str],
) -> None:
    job, content, _ = completed_generation
    job_id = cast(str, job["id"])

    restored = live_client.get(f"/api/v1/image-jobs/{job_id}")
    stored_result = live_client.get(f"/api/v1/image-jobs/{job_id}/result")

    assert restored.status_code == 200
    assert restored.json()["status"] == "completed"
    assert stored_result.content == content
    assert len(content) > 1_000


def test_live_source_only_edit_uses_provider_options(
    live_client: httpx.Client,
    completed_generation: tuple[dict[str, object], bytes, str],
) -> None:
    source_job, _, _ = completed_generation
    options = live_client.get("/api/v1/providers/image-edit/options").json()
    defaults = options["defaults"]
    response = live_client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Keep the product composition and change the surface to brushed steel",
            "aspectRatio": "4:3",
            "style": "product",
            "seed": "260802",
            "sourceJobId": source_job["id"],
            "steps": str(defaults["steps"]),
            "cfg": str(defaults["cfg"]),
            "referenceInfluence": "4",
            "groundingResolution": "768",
            "fitMode": "fit",
            "sampler": defaults["sampler"],
            "scheduler": defaults["scheduler"],
            "loras": "[]",
        },
    )
    response.raise_for_status()

    completed = _wait_for_terminal(live_client, response.json()["id"])

    assert completed["status"] == "completed"
    assert cast(dict[str, object], completed["settings"])["operation"] == "edit"


def test_live_identity_reference_edit_preserves_uploaded_input(
    live_client: httpx.Client,
    completed_generation: tuple[dict[str, object], bytes, str],
) -> None:
    source_job, content, mime_type = completed_generation
    defaults = live_client.get("/api/v1/providers/image-edit/options").json()["defaults"]
    response = live_client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Refine the light while preserving the reference subject",
            "aspectRatio": "4:3",
            "style": "editorial",
            "sourceJobId": source_job["id"],
            "steps": str(defaults["steps"]),
            "cfg": str(defaults["cfg"]),
            "referenceInfluence": "4",
            "groundingResolution": "768",
            "fitMode": "fit",
            "sampler": defaults["sampler"],
            "scheduler": defaults["scheduler"],
            "loras": "[]",
        },
        files={"faceReference": ("identity.png", content, mime_type)},
    )
    response.raise_for_status()

    completed = _wait_for_terminal(live_client, response.json()["id"])
    identity = live_client.get(f"/api/v1/image-jobs/{completed['id']}/inputs/identity")

    assert completed["status"] == "completed"
    assert cast(dict[str, object], completed["settings"])["hasFaceReference"] is True
    assert identity.content == content


def test_live_allowlisted_lora_is_recorded_when_available(
    live_client: httpx.Client,
    completed_generation: tuple[dict[str, object], bytes, str],
) -> None:
    options = live_client.get("/api/v1/providers/image-edit/options").json()
    if not options["loras"]:
        pytest.skip("No public local LoRA allowlist is configured for this runtime.")
    source_job, _, _ = completed_generation
    defaults = options["defaults"]
    selected_lora = options["loras"][0]
    response = live_client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Add restrained material detail while preserving the composition",
            "aspectRatio": "4:3",
            "style": "product",
            "sourceJobId": source_job["id"],
            "steps": str(defaults["steps"]),
            "cfg": str(defaults["cfg"]),
            "referenceInfluence": "4",
            "groundingResolution": "768",
            "fitMode": "fit",
            "sampler": defaults["sampler"],
            "scheduler": defaults["scheduler"],
            "loras": (
                '[{"id":"'
                + selected_lora["id"]
                + '","modelWeight":0.3,"clipWeight":0.3}]'
            ),
        },
    )
    response.raise_for_status()

    completed = _wait_for_terminal(live_client, response.json()["id"])

    settings = cast(dict[str, object], completed["settings"])
    edit = cast(dict[str, object], settings["edit"])
    assert cast(list[dict[str, object]], edit["loras"])[0]["id"] == selected_lora["id"]
