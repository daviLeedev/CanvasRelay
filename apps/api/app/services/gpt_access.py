from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime
from ipaddress import ip_address
from threading import RLock

from fastapi import HTTPException, Request, status


class GPTAccessGuard:
    """Small local-owner boundary until CanvasRelay has a real user identity model."""

    def __init__(
        self,
        *,
        global_daily_limit: int,
        ip_daily_limit: int,
        allow_remote_generation: bool,
        allow_docker_gateway: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.global_daily_limit = max(1, global_daily_limit)
        self.ip_daily_limit = max(1, ip_daily_limit)
        self.allow_remote_generation = allow_remote_generation
        self.allow_docker_gateway = allow_docker_gateway
        self._clock = clock or (lambda: datetime.now(UTC))
        self._counts: Counter[tuple[date, str]] = Counter()
        self._lock = RLock()

    def authorize(self, request: Request) -> None:
        host = request.client.host if request.client is not None else "unknown"
        if not self.allow_remote_generation and not is_local_owner_request(
            request, allow_docker_gateway=self.allow_docker_gateway
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This owner connection can only be used from the local computer.",
            )
        today = self._clock().date()
        with self._lock:
            self._counts = Counter(
                {key: value for key, value in self._counts.items() if key[0] == today}
            )
            global_key = (today, "*")
            ip_key = (today, host)
            if self._counts[global_key] >= self.global_daily_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="The owner GPT daily generation limit has been reached.",
                )
            if self._counts[ip_key] >= self.ip_daily_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="The local GPT generation limit for this client has been reached.",
                )
            self._counts[global_key] += 1
            self._counts[ip_key] += 1


def is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def is_local_owner_request(request: Request, *, allow_docker_gateway: bool = False) -> bool:
    """Accept host loopback and, only when configured, Docker's private bridge hop."""

    client_host = request.client.host if request.client is not None else "unknown"
    if is_loopback_host(client_host):
        return True
    if not allow_docker_gateway:
        return False
    try:
        address = ip_address(client_host)
    except ValueError:
        return False
    requested_host = request.headers.get("host", "").split(":", 1)[0].lower()
    return address.is_private and requested_host in {"localhost", "127.0.0.1", "[::1]"}
