from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.repositories.image_jobs import ImageJobRepository
from app.repositories.media import FilesystemMediaStore


def make_client(settings: Settings, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            settings,
            image_jobs=ImageJobRepository(),
            media_store=FilesystemMediaStore(tmp_path / "media"),
        )
    )


def test_health_returns_the_public_contract(tmp_path: Path) -> None:
    client = make_client(Settings(env="test", demo_mode=True), tmp_path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload.keys() == {"status", "service", "version", "demoMode", "timestamp"}
    assert payload["status"] == "ok"
    assert payload["service"] == "canvasrelay-api"
    assert payload["version"] == "0.1.0"
    assert payload["demoMode"] is True

    timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() == UTC.utcoffset(timestamp)


def test_health_reflects_demo_mode_configuration(tmp_path: Path) -> None:
    client = make_client(Settings(env="test", image_provider="comfyui"), tmp_path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["demoMode"] is False


def test_app_creates_a_missing_data_directory_before_opening_sqlite(tmp_path: Path) -> None:
    data_dir = tmp_path / "fresh" / "nested" / "data"
    settings = Settings(env="test", demo_mode=True, data_dir=data_dir)

    assert not data_dir.exists()

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert settings.database_path.is_file()
    assert settings.media_root.is_dir()
    assert settings.thumbnail_root.is_dir()
    assert settings.upload_root.is_dir()


def test_cors_allows_the_configured_web_origin(tmp_path: Path) -> None:
    origin = "http://localhost:3000"
    client = make_client(Settings(env="test", cors_origins=origin), tmp_path)

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
