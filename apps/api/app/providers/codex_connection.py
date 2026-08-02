from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

ConnectionState = Literal[
    "disconnected",
    "auth_missing",
    "starting",
    "connected",
    "reauth_required",
    "proxy_error",
]


@dataclass(frozen=True, slots=True)
class CodexConnectionStatus:
    state: ConnectionState
    message: str

    @property
    def connected(self) -> bool:
        return self.state == "connected"


ProcessFactory = Callable[..., subprocess.Popen[bytes]]


class CodexConnectionManager:
    """Owns a loopback-only OAuth proxy without persisting any credential material."""

    def __init__(
        self,
        *,
        enabled: bool,
        port: int,
        proxy_command: Path | None = None,
        repository_root: Path | None = None,
        process_factory: ProcessFactory | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.enabled = enabled
        self.port = port
        self.proxy_command = proxy_command
        self.repository_root = repository_root or self._resolve_repository_root()
        self._process_factory = process_factory or subprocess.Popen
        self._transport = transport
        self._process: subprocess.Popen[bytes] | None = None
        self._status = CodexConnectionStatus(
            "disconnected",
            "Owner Codex login is not enabled for this local server.",
        )
        self._lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def status(self) -> CodexConnectionStatus:
        return self._status

    async def import_login(self) -> CodexConnectionStatus:
        """Detect the local Codex login and start a local proxy if needed."""
        if not self.enabled:
            self._status = CodexConnectionStatus(
                "disconnected",
                "Enable the owner Codex connection in the local server configuration first.",
            )
            return self._status
        if not self._has_auth_file():
            self._status = CodexConnectionStatus(
                "auth_missing",
                "No local Codex login was found. "
                "Sign in to Codex on this computer, then check again.",
            )
            return self._status
        return await self.start()

    async def start(self) -> CodexConnectionStatus:
        async with self._lock:
            if not self.enabled:
                self._status = CodexConnectionStatus(
                    "disconnected",
                    "Owner Codex login is disabled for this local server.",
                )
                return self._status
            if not self._has_auth_file():
                self._status = CodexConnectionStatus(
                    "auth_missing",
                    "No local Codex login was found. "
                    "Sign in to Codex on this computer, then try again.",
                )
                return self._status
            existing = await self._check_locked()
            if existing.state == "connected":
                return existing
            if self._process_is_running():
                return await self._check_locked()
            command = self._command()
            if command is None:
                self._status = CodexConnectionStatus(
                    "proxy_error",
                    "The local Codex proxy package is not installed. "
                    "Install the pinned local dependency and try again.",
                )
                return self._status
            self._status = CodexConnectionStatus("starting", "Starting the local owner connection.")
            try:
                self._process = self._process_factory(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    cwd=self.repository_root,
                    creationflags=(
                        getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                    ),
                )
            except OSError:
                self._status = CodexConnectionStatus(
                    "proxy_error",
                    "CanvasRelay could not start the local owner connection.",
                )
                return self._status

            for _ in range(20):
                await asyncio.sleep(0.2)
                status = await self._check_locked()
                if status.state == "connected":
                    return status
                if self._process is not None and self._process.poll() is not None:
                    break
            self._status = CodexConnectionStatus(
                "proxy_error",
                "The local owner connection did not become ready. "
                "Check the local installation and try restart.",
            )
            return self._status

    async def check(self) -> CodexConnectionStatus:
        async with self._lock:
            return await self._check_locked()

    async def restart(self) -> CodexConnectionStatus:
        await self.disconnect()
        return await self.import_login()

    async def disconnect(self) -> CodexConnectionStatus:
        async with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait(timeout=5)
            self._process = None
            self._status = CodexConnectionStatus(
                "disconnected",
                "The local owner connection is disconnected.",
            )
            return self._status

    def mark_reauth_required(self) -> None:
        self._status = CodexConnectionStatus(
            "reauth_required",
            "The local Codex login needs to be refreshed. "
            "Sign in to Codex on this computer, then check the connection.",
        )

    async def aclose(self) -> None:
        await self.disconnect()

    async def _check_locked(self) -> CodexConnectionStatus:
        if not self.enabled:
            self._status = CodexConnectionStatus(
                "disconnected", "Owner Codex login is disabled for this local server."
            )
            return self._status
        if not self._has_auth_file():
            self._status = CodexConnectionStatus(
                "auth_missing",
                "No local Codex login was found. "
                "Sign in to Codex on this computer, then try again.",
            )
            return self._status
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=2.0,
                transport=self._transport,
            ) as client:
                response = await client.get("/v1/models")
        except httpx.HTTPError:
            self._status = CodexConnectionStatus(
                "starting" if self._process_is_running() else "proxy_error",
                "The local owner connection is not responding yet.",
            )
            return self._status
        if response.status_code in {401, 403}:
            self.mark_reauth_required()
            return self._status
        if response.is_success:
            self._status = CodexConnectionStatus(
                "connected", "Connected through the local owner Codex login."
            )
            return self._status
        self._status = CodexConnectionStatus(
            "proxy_error", "The local owner connection returned an unexpected response."
        )
        return self._status

    def _command(self) -> list[str] | None:
        node = shutil.which("node")
        entry = self.proxy_command or (
            self.repository_root / "node_modules" / "openai-oauth" / "dist" / "cli.js"
        )
        if node is None or not entry.is_file():
            return None
        # The pinned proxy defaults to loopback. Do not accept a host from browser input.
        return [node, str(entry), "--port", str(self.port)]

    def _has_auth_file(self) -> bool:
        return any(path.is_file() for path in self._auth_paths())

    def _process_is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @staticmethod
    def _auth_paths() -> tuple[Path, ...]:
        codex_home = os.environ.get("CODEX_HOME")
        home = Path.home()
        candidates = [home / ".codex" / "auth.json", home / ".config" / "codex" / "auth.json"]
        if codex_home:
            candidates.insert(0, Path(codex_home).expanduser() / "auth.json")
        return tuple(candidates)

    @staticmethod
    def _resolve_repository_root() -> Path:
        for candidate in Path(__file__).resolve().parents:
            if (candidate / "package.json").is_file():
                return candidate
        return Path.cwd()
