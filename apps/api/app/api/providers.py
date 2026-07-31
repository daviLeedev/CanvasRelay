from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.image_jobs import get_image_job_service
from app.api.schemas import ImageProviderResponse
from app.services.image_jobs import ImageJobService

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/image", response_model=ImageProviderResponse)
async def get_image_provider(
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageProviderResponse:
    descriptor = await service.describe_provider()
    return ImageProviderResponse(
        provider=descriptor.provider,
        mode="demo" if descriptor.provider == "demo" else "live",
        label=descriptor.label,
        ready=descriptor.ready,
        message=descriptor.message,
    )
