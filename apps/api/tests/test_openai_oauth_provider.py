import asyncio
import base64
from datetime import UTC, datetime
from io import BytesIO

import httpx
from PIL import Image

from app.domain.image_jobs import GPTImageSettings, ImageGenerationRequest, ProviderContent
from app.providers.codex_connection import CodexConnectionStatus
from app.providers.openai_oauth import OpenAIOAuthImageProvider


class _Connection:
    base_url = "http://owner-proxy.test"

    def __init__(self) -> None:
        self.reauth = False

    async def check(self) -> CodexConnectionStatus:
        return CodexConnectionStatus("connected", "Connected")

    def mark_reauth_required(self) -> None:
        self.reauth = True


def _png() -> bytes:
    image = Image.new("RGB", (4, 3), "white")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _request(count: int = 1) -> ImageGenerationRequest:
    return ImageGenerationRequest(
        job_id="img_gpt",
        prompt="A test image",
        aspect_ratio="1:1",
        style="editorial",
        seed=12,
        created_at=datetime.now(UTC),
        gpt_settings=GPTImageSettings(count=count),
    )


def test_collects_one_or_two_base64_images_and_keeps_reference_order() -> None:
    body = _png()
    encoded = base64.b64encode(body).decode("ascii")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "image-runtime"}]})
        return httpx.Response(200, json={"output": [{"result": encoded}]})

    async def run() -> None:
        provider = OpenAIOAuthImageProvider(_Connection(), transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
        provider_job_id = await provider.submit_with_references(
            _request(count=2),
            (ProviderContent(body, "image/png"), ProviderContent(body, "image/png")),
        )
        await asyncio.sleep(0)
        snapshot = await provider.poll(provider_job_id)
        assert snapshot.status == "completed"
        results = await provider.collect_many(provider_job_id)
        assert len(results) == 2
        assert all(result.mime_type == "image/png" for result in results)

    asyncio.run(run())
    response_requests = [item for item in calls if item.url.path == "/v1/responses"]
    assert len(response_requests) == 2
    assert b"input_image" in response_requests[0].content


def test_unauthorized_response_requires_reauthentication_without_retry() -> None:
    connection = _Connection()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(403, json={"error": "unauthorized"})

    async def run() -> None:
        provider = OpenAIOAuthImageProvider(connection, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
        provider_job_id = await provider.submit(_request())
        await asyncio.sleep(0)
        snapshot = await provider.poll(provider_job_id)
        assert snapshot.status == "failed"
        assert snapshot.error is not None and snapshot.error.code == "reauth_required"

    asyncio.run(run())
    assert connection.reauth is True
    assert calls == 2
