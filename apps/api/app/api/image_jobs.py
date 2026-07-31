from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.schemas import (
    ImageJobCreate,
    ImageJobError,
    ImageJobResponse,
    ImageJobResult,
    ImageJobSettings,
)
from app.domain.image_jobs import ImageJobRecord
from app.providers.base import ImageProviderError
from app.repositories.image_jobs import ImageJobNotFoundError
from app.services.image_jobs import ImageJobService

router = APIRouter(prefix="/image-jobs", tags=["image jobs"])


def get_image_job_service(request: Request) -> ImageJobService:
    return cast(ImageJobService, request.app.state.image_job_service)


def _to_response(record: ImageJobRecord) -> ImageJobResponse:
    result = None
    if record.status == "completed" and record.result is not None:
        result = ImageJobResult(
            url=f"/api/v1/image-jobs/{record.id}/result",
            mimeType=record.result.mime_type,
            width=record.result.width,
            height=record.result.height,
        )
    error = None
    if record.error is not None:
        error = ImageJobError(
            code=record.error.code,
            message=record.error.message,
            action=record.error.action,
            retryable=record.error.retryable,
        )
    return ImageJobResponse(
        id=record.id,
        status=record.status,
        progress=record.progress,
        prompt=record.prompt,
        settings=ImageJobSettings(
            aspectRatio=record.aspect_ratio,
            style=record.style,
            seed=record.seed,
            provider=record.provider,
        ),
        createdAt=record.created_at,
        startedAt=record.started_at,
        completedAt=record.completed_at,
        result=result,
        error=error,
    )


def _not_found(error: ImageJobNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="Image job was not found.")


def _provider_unavailable(error: ImageProviderError) -> HTTPException:
    conflict_codes = {
        "result_not_ready",
        "workflow_missing",
        "workflow_invalid",
        "workflow_bindings_missing",
    }
    return HTTPException(
        status_code=409 if error.details.code in conflict_codes else 503,
        detail={
            "code": error.details.code,
            "message": error.details.message,
            "action": error.details.action,
        },
    )


@router.post("", response_model=ImageJobResponse, status_code=status.HTTP_201_CREATED)
async def create_image_job(
    payload: ImageJobCreate,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageJobResponse:
    record = await service.create(
        prompt=payload.prompt,
        aspect_ratio=payload.aspect_ratio,
        style=payload.style,
        seed=payload.seed,
    )
    return _to_response(record)


@router.get("/{job_id}", response_model=ImageJobResponse)
async def get_image_job(
    job_id: str,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageJobResponse:
    try:
        return _to_response(await service.get(job_id))
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error


@router.delete("/{job_id}", response_model=ImageJobResponse)
async def cancel_image_job(
    job_id: str,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageJobResponse:
    try:
        return _to_response(await service.cancel(job_id))
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error


@router.get("/{job_id}/result", response_class=Response)
async def get_image_job_result(
    job_id: str,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> Response:
    try:
        content = await service.collect(job_id)
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error
    return Response(
        content=content.body,
        media_type=content.mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
