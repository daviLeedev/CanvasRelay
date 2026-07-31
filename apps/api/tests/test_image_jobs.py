from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.demo import DemoImageProvider
from app.repositories.image_jobs import ImageJobRepository
from app.repositories.media import FilesystemMediaStore, FilesystemUploadStore


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, *, milliseconds: int) -> None:
        self.current += timedelta(milliseconds=milliseconds)


def make_client(
    clock: MutableClock,
    tmp_path: Path,
    *,
    database_path: Path | str = ":memory:",
) -> TestClient:
    repository = ImageJobRepository(clock, database_path)
    provider = DemoImageProvider(clock)
    return TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=repository,
            image_provider=provider,
            media_store=FilesystemMediaStore(tmp_path / "media"),
            upload_store=FilesystemUploadStore(tmp_path / "uploads"),
        )
    )


def create_job(client: TestClient, *, prompt: str = "A precise studio still") -> dict[str, object]:
    response = client.post(
        "/api/v1/image-jobs",
        json={"prompt": prompt, "aspectRatio": "4:3", "style": "editorial", "seed": 42},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


def test_create_validates_input_and_returns_a_typed_queued_job(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)

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
        "operation": "generate",
        "hasFaceReference": False,
        "sourceJobId": None,
        "edit": None,
    }
    assert created["result"] is None
    assert created["error"] is None


def test_image_provider_status_is_public_and_redacted(tmp_path: Path) -> None:
    client = make_client(MutableClock(), tmp_path)

    response = client.get("/api/v1/providers/image")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "demo",
        "mode": "demo",
        "label": "Deterministic demo",
        "ready": True,
        "message": "Ready without a GPU or model files.",
    }


def test_job_moves_from_queued_to_running_to_completed_from_elapsed_time(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    job_id = create_job(client)["id"]

    clock.advance(milliseconds=1400)
    running = client.get(f"/api/v1/image-jobs/{job_id}").json()
    clock.advance(milliseconds=3000)
    completed = client.get(f"/api/v1/image-jobs/{job_id}").json()

    assert running["status"] == "running"
    assert 1 <= running["progress"] <= 95
    assert running["startedAt"] is not None
    assert completed["status"] == "completed"
    assert completed["progress"] == 100
    assert completed["completedAt"] is not None
    assert completed["result"]["mimeType"] == "image/svg+xml"


def test_cancel_is_terminal_and_prevents_later_completion(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    job_id = create_job(client)["id"]

    clock.advance(milliseconds=1000)
    canceled = client.delete(f"/api/v1/image-jobs/{job_id}").json()
    clock.advance(milliseconds=10_000)
    later = client.get(f"/api/v1/image-jobs/{job_id}").json()

    assert canceled["status"] == "canceled"
    assert later["status"] == "canceled"
    assert later["result"] is None
    assert client.get(f"/api/v1/image-jobs/{job_id}/result").status_code == 409


def test_unknown_job_returns_a_safe_not_found_response(tmp_path: Path) -> None:
    client = make_client(MutableClock(), tmp_path)

    response = client.get("/api/v1/image-jobs/img_missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Image job was not found."}


def test_result_is_deterministic_nonempty_and_escapes_the_prompt(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
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


def test_recent_jobs_are_listed_newest_first(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    first = create_job(client, prompt="First composition")
    clock.advance(milliseconds=10)
    second = create_job(client, prompt="Second composition")

    response = client.get("/api/v1/image-jobs?limit=2")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [second["id"], first["id"]]


def test_completed_filter_refreshes_jobs_that_finished_while_no_client_was_open(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    job = create_job(client)
    clock.advance(milliseconds=4000)

    response = client.get("/api/v1/image-jobs?status=completed&limit=10")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [job["id"]]


def test_completed_job_and_result_survive_api_restart(tmp_path: Path) -> None:
    clock = MutableClock()
    database_path = tmp_path / "canvasrelay.sqlite3"
    media_store = FilesystemMediaStore(tmp_path / "media")
    first_repository = ImageJobRepository(clock, database_path)
    first_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=first_repository,
            image_provider=DemoImageProvider(clock),
            media_store=media_store,
        )
    )
    job_id = cast(str, create_job(first_client)["id"])
    clock.advance(milliseconds=4000)
    first_result = first_client.get(f"/api/v1/image-jobs/{job_id}/result")
    first_repository.close()

    second_repository = ImageJobRepository(clock, database_path)
    second_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=second_repository,
            image_provider=DemoImageProvider(clock),
            media_store=media_store,
        )
    )
    restored = second_client.get(f"/api/v1/image-jobs/{job_id}")
    second_result = second_client.get(f"/api/v1/image-jobs/{job_id}/result")

    assert restored.status_code == 200
    assert restored.json()["status"] == "completed"
    assert second_result.content == first_result.content
    second_repository.close()


def test_completed_job_event_stream_emits_typed_snapshot(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    job_id = create_job(client)["id"]
    clock.advance(milliseconds=4000)

    response = client.get(f"/api/v1/image-jobs/{job_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: job" in response.text
    assert '"status":"completed"' in response.text


def test_image_edit_accepts_source_and_optional_face_reference(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    image = b"\x89PNG\r\n\x1a\ncanvasrelay-test"

    response = client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Replace the background with a quiet studio wall",
            "aspectRatio": "4:3",
            "style": "editorial",
            "seed": "91",
        },
        files={
            "source": ("source.png", image, "image/png"),
            "faceReference": ("face.png", image, "image/png"),
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["settings"]["operation"] == "edit"
    assert payload["settings"]["hasFaceReference"] is True
    assert list((tmp_path / "uploads").glob(f"{payload['id']}_source.png"))
    assert list((tmp_path / "uploads").glob(f"{payload['id']}_face.png"))

    listed = client.get("/api/v1/image-jobs?operation=edit").json()["items"]
    assert [item["id"] for item in listed] == [payload["id"]]


def test_image_edit_rejects_invalid_upload_without_exposing_internals(tmp_path: Path) -> None:
    client = make_client(MutableClock(), tmp_path)

    response = client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Use a clean studio background",
            "aspectRatio": "1:1",
            "style": "product",
        },
        files={"source": ("source.txt", b"not-an-image", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Choose a valid PNG, JPEG, or WebP image."}


def test_library_result_handoff_uses_server_owned_source_and_restores_settings(
    tmp_path: Path,
) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    source_id = str(create_job(client)["id"])
    clock.advance(milliseconds=4000)
    assert client.get(f"/api/v1/image-jobs/{source_id}").json()["status"] == "completed"

    response = client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Refine the scene with softer light",
            "aspectRatio": "4:3",
            "style": "editorial",
            "sourceJobId": source_id,
            "steps": "10",
            "cfg": "1.4",
            "referenceInfluence": "5.2",
            "groundingResolution": "1024",
            "fitMode": "crop",
            "sampler": "dpmpp_2m",
            "scheduler": "karras",
            "loras": '[{"id":"demo-detail","modelWeight":0.7,"clipWeight":0.3}]',
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["settings"]["sourceJobId"] == source_id
    assert payload["settings"]["edit"] == {
        "steps": 10,
        "cfg": 1.4,
        "referenceInfluence": 5.2,
        "groundingResolution": 1024,
        "fitMode": "crop",
        "sampler": "dpmpp_2m",
        "scheduler": "karras",
        "loras": [{"id": "demo-detail", "modelWeight": 0.7, "clipWeight": 0.3}],
    }
    input_response = client.get(f"/api/v1/image-jobs/{payload['id']}/inputs/source")
    assert input_response.status_code == 200
    assert input_response.headers["content-type"].startswith("image/svg+xml")


def test_image_edit_requires_exactly_one_server_or_upload_source(tmp_path: Path) -> None:
    client = make_client(MutableClock(), tmp_path)
    image = b"\x89PNG\r\n\x1a\ncanvasrelay-test"

    missing = client.post(
        "/api/v1/image-edit-jobs",
        data={"prompt": "Refine", "aspectRatio": "1:1", "style": "editorial"},
    )
    duplicate = client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Refine",
            "aspectRatio": "1:1",
            "style": "editorial",
            "sourceJobId": "img_untrusted",
        },
        files={"source": ("source.png", image, "image/png")},
    )

    assert missing.status_code == 422
    assert duplicate.status_code == 422
