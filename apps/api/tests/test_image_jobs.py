from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.image_jobs import ImageGenerationRequest, ProviderErrorDetails, ProviderSnapshot
from app.main import create_app
from app.providers.base import ImageProviderError
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


class RestartableDemoProvider(DemoImageProvider):
    def __init__(self, clock: MutableClock, *, available: bool = True) -> None:
        super().__init__(clock)
        self.available = available

    async def poll(self, provider_job_id: str) -> ProviderSnapshot:
        if not self.available:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "provider_unavailable",
                    "The local provider is unavailable.",
                    "Start the provider and retry later.",
                    True,
                )
            )
        return await super().poll(provider_job_id)


class ProviderRestartedDemoProvider(DemoImageProvider):
    async def poll(self, provider_job_id: str) -> ProviderSnapshot:
        del provider_job_id
        raise ImageProviderError(
            ProviderErrorDetails(
                "provider_restarted",
                "The inference provider restarted before this job completed.",
                "Your settings were preserved. Retry the job when the provider is ready.",
                True,
            )
        )


class FailingOnceDemoProvider(DemoImageProvider):
    def __init__(self, clock: MutableClock) -> None:
        super().__init__(clock)
        self.submit_count = 0

    async def submit(self, request: ImageGenerationRequest) -> str:
        self.submit_count += 1
        if self.submit_count == 1:
            raise ImageProviderError(
                ProviderErrorDetails(
                    "provider_restarted",
                    "The inference provider restarted before this job completed.",
                    "Your settings were preserved. Retry the job when the provider is ready.",
                    True,
                )
            )
        return await super().submit(request)


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
        "gpt": None,
        "generation": {
            "steps": 8,
            "cfg": 1.0,
            "shift": 5.0,
            "sampler": "euler",
            "scheduler": "beta",
            "loras": [],
        },
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


def test_result_supports_etag_conditional_and_range_requests(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    job_id = create_job(client)["id"]
    clock.advance(milliseconds=4000)

    first = client.get(f"/api/v1/image-jobs/{job_id}/result")
    conditional = client.get(
        f"/api/v1/image-jobs/{job_id}/result",
        headers={"If-None-Match": first.headers["etag"]},
    )
    partial = client.get(
        f"/api/v1/image-jobs/{job_id}/result",
        headers={"Range": "bytes=0-15"},
    )

    assert first.status_code == 200
    assert first.headers["content-length"] == str(len(first.content))
    assert first.headers["etag"].startswith('"sha256-')
    assert conditional.status_code == 304
    assert partial.status_code == 206
    assert partial.headers["content-range"].startswith("bytes 0-15/")
    assert len(partial.content) == 16


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


def test_job_list_uses_a_stable_cursor_without_repeating_items(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    created: list[str] = []
    for prompt in ("First", "Second", "Third"):
        created.append(cast(str, create_job(client, prompt=prompt)["id"]))
        clock.advance(milliseconds=10)

    first_page = client.get("/api/v1/image-jobs?limit=2").json()
    second_page = client.get(
        "/api/v1/image-jobs",
        params={"limit": 2, "cursor": first_page["nextCursor"]},
    ).json()

    assert [item["id"] for item in first_page["items"]] == list(reversed(created[1:]))
    assert [item["id"] for item in second_page["items"]] == [created[0]]
    assert second_page["nextCursor"] is None
    assert client.get("/api/v1/image-jobs?cursor=not-a-cursor").status_code == 422


def test_library_search_and_tags_are_persistent_and_filterable(tmp_path: Path) -> None:
    clock = MutableClock()
    database_path = tmp_path / "canvasrelay.sqlite3"
    client = make_client(clock, tmp_path, database_path=database_path)
    first = create_job(client, prompt="Architectural daylight portrait")
    second = create_job(client, prompt="Studio product layout")
    clock.advance(milliseconds=4000)
    assert client.get(f"/api/v1/image-jobs/{first['id']}/result").status_code == 200
    assert client.get(f"/api/v1/image-jobs/{second['id']}/result").status_code == 200

    tagged = client.patch(
        f"/api/v1/image-jobs/{first['id']}/tags",
        json={"tags": ["Portrait", "  Client   Review  ", "portrait"]},
    )

    assert tagged.status_code == 200
    assert tagged.json()["tags"] == ["client review", "portrait"]
    assert client.get("/api/v1/image-jobs/tags").json() == {
        "tags": ["client review", "portrait"]
    }
    searched = client.get("/api/v1/image-jobs", params={"search": "daylight"})
    filtered = client.get("/api/v1/image-jobs", params={"tag": "PORTRAIT"})
    assert [item["id"] for item in searched.json()["items"]] == [first["id"]]
    assert [item["id"] for item in filtered.json()["items"]] == [first["id"]]

    restarted = make_client(clock, tmp_path, database_path=database_path)
    assert restarted.get(f"/api/v1/image-jobs/{first['id']}").json()["tags"] == [
        "client review",
        "portrait",
    ]


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


def test_completed_library_asset_requires_explicit_delete(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    job_id = cast(str, create_job(client)["id"])
    clock.advance(milliseconds=4000)
    assert client.get(f"/api/v1/image-jobs/{job_id}/result").status_code == 200

    deleted = client.delete(f"/api/v1/image-jobs/{job_id}/asset")

    assert deleted.status_code == 204
    assert client.get(f"/api/v1/image-jobs/{job_id}").status_code == 404
    assert not list((tmp_path / "media").glob(f"{job_id}.*"))


def test_completed_library_assets_can_be_deleted_as_a_batch(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    job_ids = [cast(str, create_job(client, prompt=prompt)["id"]) for prompt in ("First", "Second")]
    clock.advance(milliseconds=4000)
    for job_id in job_ids:
        assert client.get(f"/api/v1/image-jobs/{job_id}/result").status_code == 200

    deleted = client.post("/api/v1/image-jobs/assets/delete", json={"ids": job_ids})

    assert deleted.status_code == 200
    assert deleted.json() == {"deletedIds": job_ids}
    assert all(client.get(f"/api/v1/image-jobs/{job_id}").status_code == 404 for job_id in job_ids)


def test_library_asset_cannot_be_deleted_while_an_edit_references_it(tmp_path: Path) -> None:
    clock = MutableClock()
    client = make_client(clock, tmp_path)
    source_id = cast(str, create_job(client)["id"])
    clock.advance(milliseconds=4000)
    assert client.get(f"/api/v1/image-jobs/{source_id}/result").status_code == 200
    edit = client.post(
        "/api/v1/image-edit-jobs",
        data={
            "prompt": "Refine the lighting",
            "aspectRatio": "4:3",
            "style": "editorial",
            "sourceJobId": source_id,
        },
    )
    assert edit.status_code == 201

    response = client.delete(f"/api/v1/image-jobs/{source_id}/asset")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "asset_in_use"
    assert client.get(f"/api/v1/image-jobs/{source_id}").status_code == 200


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


def test_completed_library_survives_provider_restart(tmp_path: Path) -> None:
    clock = MutableClock()
    database_path = tmp_path / "canvasrelay.sqlite3"
    media_store = FilesystemMediaStore(tmp_path / "media")
    first_repository = ImageJobRepository(clock, database_path)
    first_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=first_repository,
            image_provider=RestartableDemoProvider(clock),
            media_store=media_store,
        )
    )
    job_id = cast(str, create_job(first_client)["id"])
    clock.advance(milliseconds=4000)
    assert first_client.get(f"/api/v1/image-jobs/{job_id}/result").status_code == 200
    active_job_id = cast(str, create_job(first_client, prompt="Keep this active job")["id"])
    first_repository.close()

    restarted_repository = ImageJobRepository(clock, database_path)
    restarted_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=restarted_repository,
            image_provider=RestartableDemoProvider(clock, available=False),
            media_store=media_store,
        )
    )

    library = restarted_client.get("/api/v1/image-jobs?status=completed")
    result = restarted_client.get(f"/api/v1/image-jobs/{job_id}/result")
    active = restarted_client.get(f"/api/v1/image-jobs/{active_job_id}")

    assert library.status_code == 200
    assert [item["id"] for item in library.json()["items"]] == [job_id]
    assert result.status_code == 200
    assert active.status_code == 200
    assert active.json()["stalled"] is True
    restarted_repository.close()


def test_active_job_stays_visible_when_provider_is_restarting(tmp_path: Path) -> None:
    clock = MutableClock()
    database_path = tmp_path / "canvasrelay.sqlite3"
    first_repository = ImageJobRepository(clock, database_path)
    first_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=first_repository,
            image_provider=RestartableDemoProvider(clock),
            media_store=FilesystemMediaStore(tmp_path / "media"),
        )
    )
    job_id = cast(str, create_job(first_client)["id"])
    first_repository.close()

    restarted_repository = ImageJobRepository(clock, database_path)
    restarted_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=restarted_repository,
            image_provider=RestartableDemoProvider(clock, available=False),
            media_store=FilesystemMediaStore(tmp_path / "media"),
        )
    )

    recent = restarted_client.get("/api/v1/image-jobs")
    restored = restarted_client.get(f"/api/v1/image-jobs/{job_id}")

    assert recent.status_code == 200
    assert recent.json()["items"][0]["id"] == job_id
    assert restored.status_code == 200
    assert restored.json()["status"] == "queued"
    assert restored.json()["stalled"] is True
    restarted_repository.close()


def test_missing_provider_job_becomes_retryable_failed_record_after_restart(tmp_path: Path) -> None:
    clock = MutableClock()
    database_path = tmp_path / "canvasrelay.sqlite3"
    first_repository = ImageJobRepository(clock, database_path)
    first_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=first_repository,
            image_provider=DemoImageProvider(clock),
            media_store=FilesystemMediaStore(tmp_path / "media"),
        )
    )
    job_id = cast(str, create_job(first_client)["id"])
    first_repository.close()

    restarted_repository = ImageJobRepository(clock, database_path)
    restarted_client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=restarted_repository,
            image_provider=ProviderRestartedDemoProvider(clock),
            media_store=FilesystemMediaStore(tmp_path / "media"),
        )
    )

    restored = restarted_client.get(f"/api/v1/image-jobs/{job_id}")
    failed = restarted_client.get("/api/v1/image-jobs?status=failed")

    assert restored.status_code == 200
    assert restored.json()["status"] == "failed"
    assert restored.json()["error"] == {
        "code": "provider_restarted",
        "message": "The inference provider restarted before this job completed.",
        "action": "Your settings were preserved. Retry the job when the provider is ready.",
        "retryable": True,
    }
    assert [item["id"] for item in failed.json()["items"]] == [job_id]
    restarted_repository.close()


def test_retry_creates_a_new_job_from_persisted_failed_settings(tmp_path: Path) -> None:
    clock = MutableClock()
    provider = FailingOnceDemoProvider(clock)
    client = TestClient(
        create_app(
            Settings(env="test"),
            image_jobs=ImageJobRepository(clock),
            image_provider=provider,
            media_store=FilesystemMediaStore(tmp_path / "media"),
        )
    )
    failed = create_job(client, prompt="Retry this durable request")

    response = client.post(f"/api/v1/image-jobs/{failed['id']}/retry")

    assert failed["status"] == "failed"
    assert response.status_code == 201
    retried = response.json()
    assert retried["id"] != failed["id"]
    assert retried["status"] == "queued"
    assert retried["prompt"] == failed["prompt"]
    retried_settings = cast(dict[str, object], retried["settings"])
    failed_settings = cast(dict[str, object], failed["settings"])
    assert retried_settings["seed"] == failed_settings["seed"]


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
