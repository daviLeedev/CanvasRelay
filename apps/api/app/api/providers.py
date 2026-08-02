from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.image_jobs import get_image_job_service
from app.api.schemas import (
    ImageEditLoraOption,
    ImageEditOptionDefaults,
    ImageEditProviderOptionsResponse,
    ImageGenerationOptionDefaults,
    ImageGenerationProviderOptionsResponse,
    ImageProviderResponse,
)
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


@router.get("/image-edit", response_model=ImageProviderResponse)
async def get_image_edit_provider(
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageProviderResponse:
    descriptor = await service.describe_edit_provider()
    return ImageProviderResponse(
        provider=descriptor.provider,
        mode="demo" if descriptor.provider == "demo" else "live",
        label=descriptor.label,
        ready=descriptor.ready,
        message=descriptor.message,
    )


@router.get("/image-edit/options", response_model=ImageEditProviderOptionsResponse)
async def get_image_edit_options(
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageEditProviderOptionsResponse:
    options = await service.describe_edit_options()
    return ImageEditProviderOptionsResponse(
        samplers=list(options.samplers),
        schedulers=list(options.schedulers),
        loras=[ImageEditLoraOption(id=item.id, label=item.label) for item in options.loras],
        defaults=ImageEditOptionDefaults(
            steps=options.default_steps,
            cfg=options.default_cfg,
            sampler=options.default_sampler,
            scheduler=options.default_scheduler,
        ),
    )


@router.get("/image/options", response_model=ImageGenerationProviderOptionsResponse)
async def get_image_generation_options(
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageGenerationProviderOptionsResponse:
    options = await service.describe_generation_options()
    return ImageGenerationProviderOptionsResponse(
        samplers=list(options.samplers),
        schedulers=list(options.schedulers),
        loras=[ImageEditLoraOption(id=item.id, label=item.label) for item in options.loras],
        defaults=ImageGenerationOptionDefaults(
            steps=options.default_steps,
            cfg=options.default_cfg,
            shift=options.default_shift,
            sampler=options.default_sampler,
            scheduler=options.default_scheduler,
        ),
    )
