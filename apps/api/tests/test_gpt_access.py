from fastapi import Request

from app.services.gpt_access import is_local_owner_request


def _request(client_host: str, host_header: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", host_header.encode("ascii"))],
            "client": (client_host, 41000),
        }
    )


def test_owner_connection_accepts_loopback_requests() -> None:
    assert is_local_owner_request(_request("127.0.0.1", "127.0.0.1:8000"))


def test_owner_connection_only_accepts_docker_gateway_when_explicitly_enabled() -> None:
    request = _request("172.20.0.1", "localhost:8000")

    assert not is_local_owner_request(request)
    assert is_local_owner_request(request, allow_docker_gateway=True)
    assert not is_local_owner_request(
        _request("172.20.0.1", "canvasrelay.local:8000"),
        allow_docker_gateway=True,
    )
