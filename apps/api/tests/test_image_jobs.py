from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.demo import DemoImageProvider
from app.repositories.image_jobs import ImageJobRepository


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, *, milliseconds: int) -> None:
        self.current += timedelta(milliseconds=milliseconds)


def make_client(clock: MutableClock) -> TestClient:
    repository = ImageJobRepository(clock)
    provider = DemoImageProvider(clock)
    return TestClient(
        create_app(Settings(env="test"), image_jobs=repository, image_provider=provider)
    )


def create_job(client: TestClient, *, prompt: str = "A precise studio still") -> dict[str, object]:
    response = client.post(
        "/api/v1/image-jobs",
        json={"prompt": prompt, "aspectRatio": "4:3", "style": "editorial", "seed": 42},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_create_validates_input_and_returns_a_typed_queued_job() -> None:
    clock = MutableClock()
    client = make_client(clock)

    invalid = client.post(
        "/api/v1/image-jobs",
        json={"prompt": "   ", "aspectRatio": "panorama", "style": "unknown"},
    )
    created = create_job(client)

    assert invalid.status_code == 422
    assert created["status"] == "queued"
    assert created["progress"] == 0
    assert created["settings"] == {
        "aspectRatio": "4:3",
        "style": "editorial",
        "seed": 42,
        "provider": "demo",
    }
    assert created["result"] is None
    assert created["error"] is None


def test_image_provider_status_is_public_and_redacted() -> None:
    client = make_client(MutableClock())

    response = client.get("/api/v1/providers/image")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "demo",
        "mode": "demo",
        "label": "Deterministic demo",
        "ready": True,
        "message": "Ready without a GPU or model files.",
    }


def test_job_moves_from_queued_to_running_to_completed_from_elapsed_time() -> None:
    clock = MutableClock()
    client = make_client(clock)
    job_id = create_job(client)["id"]

    clock.advance(milliseconds=900)
    running = client.get(f"/api/v1/image-jobs/{job_id}").json()
    clock.advance(milliseconds=3000)
    completed = client.get(f"/api/v1/image-jobs/{job_id}").json()

    assert running["status"] == "running"
    assert 8 <= running["progress"] <= 95
    assert running["startedAt"] is not None
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["completedAt"] is not None
    assert completed["result"]["mimeType"] == "image/svg+xml"


def test_cancel_is_terminal_and_prevents_later_completion() -> None:
    clock = MutableClock()
    client = make_client(clock)
    job_id = create_job(client)["id"]

    clock.advance(milliseconds=1000)
    canceled = client.delete(f"/api/v1/image-jobs/{job_id}").json()
    clock.advance(milliseconds=10_000)
    later = client.get(f"/api/v1/image-jobs/{job_id}").json()

    assert canceled["status"] == "canceled"
    assert later["status"] == "canceled"
    assert later["result"] is None
    assert client.get(f"/api/v1/image-jobs/{job_id}/result").status_code == 409


def test_unknown_job_returns_a_safe_not_found_response() -> None:
    client = make_client(MutableClock())

    response = client.get("/api/v1/image-jobs/img_missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Image job was not found."}


def test_result_is_deterministic_nonempty_and_escapes_the_prompt() -> None:
    clock = MutableClock()
    client = make_client(clock)
    prompt = '<script>alert("demo")</script> structured portrait'
    first_id = create_job(client, prompt=prompt)["id"]
    second_id = create_job(client, prompt=prompt)["id"]
    clock.advance(milliseconds=4000)

    first = client.get(f"/api/v1/image-jobs/{first_id}/result")
    second = client.get(f"/api/v1/image-jobs/{second_id}/result")

    assert first.status_code == 200
    assert first.headers["content-type"].startswith("image/svg+xml")
    assert first.text == second.text
    assert len(first.text) > 1000
    assert '<script>' not in first.text
    assert "&lt;script&gt;" in first.text
    assert len(set(first.text)) > 20
