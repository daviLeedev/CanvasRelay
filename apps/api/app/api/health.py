from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.schemas import HealthResponse
from app.core.config import Settings, get_request_settings

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Annotated[Settings, Depends(get_request_settings)],
) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="canvasrelay-api",
        version=settings.app_version,
        demoMode=settings.demo_mode,
        timestamp=datetime.now(UTC),
    )
