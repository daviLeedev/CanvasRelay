import asyncio
from pathlib import Path

import httpx
from pytest import MonkeyPatch

from app.providers.codex_connection import CodexConnectionManager


class _Process:
    def __init__(self) -> None:
        self.running = True

    def poll(self) -> int | None:
        return None if self.running else 0

    def terminate(self) -> None:
        self.running = False

    def wait(self, timeout: float) -> int:
        del timeout
        return 0

    def kill(self) -> None:
        self.running = False


def test_missing_local_auth_does_not_start_proxy() -> None:
    manager = CodexConnectionManager(enabled=True, port=18765)
    status = asyncio.run(manager.import_login())
    assert status.state == "auth_missing"
    assert "token" not in status.message.casefold()


def test_connected_proxy_is_reused_without_duplicate_process(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text("{}")
    starts = 0

    def factory(*args: object, **kwargs: object) -> _Process:
        nonlocal starts
        del args, kwargs
        starts += 1
        return _Process()

    monkeypatch.setattr(
        CodexConnectionManager,
        "_auth_paths",
        staticmethod(lambda: (auth_file,)),
    )
    manager = CodexConnectionManager(
        enabled=True,
        port=18765,
        process_factory=factory,  # type: ignore[arg-type]
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []})),
    )
    status = asyncio.run(manager.start())
    assert status.state == "connected"
    assert starts == 0
    assert "auth.json" not in status.message


def test_unauthorized_proxy_marks_reauthentication_required(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    auth_file = tmp_path / "auth.json"
    auth_file.write_text("{}")
    monkeypatch.setattr(
        CodexConnectionManager,
        "_auth_paths",
        staticmethod(lambda: (auth_file,)),
    )
    manager = CodexConnectionManager(
        enabled=True,
        port=18765,
        transport=httpx.MockTransport(lambda request: httpx.Response(401)),
    )
    status = asyncio.run(manager.check())
    assert status.state == "reauth_required"
    assert "401" not in status.message
