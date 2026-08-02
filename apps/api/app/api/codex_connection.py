from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.schemas import CodexConnectionResponse
from app.core.config import Settings, get_request_settings
from app.providers.codex_connection import CodexConnectionManager, CodexConnectionStatus
from app.services.gpt_access import is_local_owner_request

router = APIRouter(prefix="/connections/codex", tags=["owner codex connection"])


def get_codex_connection(request: Request) -> CodexConnectionManager:
    return cast(CodexConnectionManager, request.app.state.codex_connection)


def require_local_management(request: Request) -> None:
    settings: Settings = get_request_settings(request)
    if not settings.codex_oauth_allow_remote_management and not is_local_owner_request(
        request, allow_docker_gateway=settings.codex_oauth_allow_docker_gateway
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner connection management is only available on the local computer.",
        )


def _response(value: CodexConnectionStatus) -> CodexConnectionResponse:
    return CodexConnectionResponse(
        state=value.state, connected=value.connected, message=value.message
    )


@router.get("", response_model=CodexConnectionResponse)
async def get_connection_status(
    _: Annotated[None, Depends(require_local_management)],
    connection: Annotated[CodexConnectionManager, Depends(get_codex_connection)],
) -> CodexConnectionResponse:
    return _response(connection.status())


@router.post("/import", response_model=CodexConnectionResponse)
async def import_connection(
    _: Annotated[None, Depends(require_local_management)],
    connection: Annotated[CodexConnectionManager, Depends(get_codex_connection)],
) -> CodexConnectionResponse:
    return _response(await connection.import_login())


@router.post("/check", response_model=CodexConnectionResponse)
async def check_connection(
    _: Annotated[None, Depends(require_local_management)],
    connection: Annotated[CodexConnectionManager, Depends(get_codex_connection)],
) -> CodexConnectionResponse:
    return _response(await connection.check())


@router.post("/restart", response_model=CodexConnectionResponse)
async def restart_connection(
    _: Annotated[None, Depends(require_local_management)],
    connection: Annotated[CodexConnectionManager, Depends(get_codex_connection)],
) -> CodexConnectionResponse:
    return _response(await connection.restart())


@router.delete("", response_model=CodexConnectionResponse)
async def disconnect_connection(
    _: Annotated[None, Depends(require_local_management)],
    connection: Annotated[CodexConnectionManager, Depends(get_codex_connection)],
) -> CodexConnectionResponse:
    return _response(await connection.disconnect())
