from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_returns_the_public_contract() -> None:
    client = TestClient(create_app(Settings(env="test", demo_mode=True)))

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


def test_health_reflects_demo_mode_configuration() -> None:
    client = TestClient(create_app(Settings(env="test", demo_mode=False)))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["demoMode"] is False


def test_cors_allows_the_configured_web_origin() -> None:
    origin = "http://localhost:3000"
    client = TestClient(create_app(Settings(env="test", cors_origins=origin)))

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
