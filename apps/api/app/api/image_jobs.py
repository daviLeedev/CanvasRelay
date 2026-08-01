import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from app.api.schemas import (
    ImageEditSettingsResponse,
    ImageJobCreate,
    ImageJobError,
    ImageJobListResponse,
    ImageJobResponse,
    ImageJobResult,
    ImageJobSettings,
    LoraSelectionResponse,
)
from app.domain.image_jobs import ImageJobOperation, ImageJobRecord, ImageJobStatus
from app.providers.base import ImageProviderError
from app.repositories.image_jobs import (
    TERMINAL_STATUSES,
    ImageJobNotFoundError,
    InvalidImageJobCursorError,
)
from app.repositories.media import StoredMediaFile
from app.services.image_jobs import ImageJobService

router = APIRouter(prefix="/image-jobs", tags=["image jobs"])


def get_image_job_service(request: Request) -> ImageJobService:
    return cast(ImageJobService, request.app.state.image_job_service)


def _to_response(record: ImageJobRecord) -> ImageJobResponse:
    result = None
    if record.status == "completed" and record.result is not None:
        result = ImageJobResult(
            url=f"/api/v1/image-jobs/{record.id}/result",
            thumbnailUrl=(
                f"/api/v1/image-jobs/{record.id}/thumbnail"
                if record.thumbnail_path is not None
                else f"/api/v1/image-jobs/{record.id}/result"
            ),
            mimeType=record.result.mime_type,
            width=record.result.width,
            height=record.result.height,
            sizeBytes=record.result_size_bytes,
            sha256=record.result_sha256,
            available=not record.result_missing,
        )
    error = None
    if record.error is not None:
        error = ImageJobError(
            code=record.error.code,
            message=record.error.message,
            action=record.error.action,
            retryable=record.error.retryable,
        )
    edit = None
    if record.edit_settings is not None:
        edit = ImageEditSettingsResponse(
            steps=record.edit_settings.steps,
            cfg=record.edit_settings.cfg,
            referenceInfluence=record.edit_settings.reference_influence,
            groundingResolution=record.edit_settings.grounding_resolution,
            fitMode=record.edit_settings.fit_mode,
            sampler=record.edit_settings.sampler,
            scheduler=record.edit_settings.scheduler,
            loras=[
                LoraSelectionResponse(
                    id=item.id,
                    modelWeight=item.model_weight,
                    clipWeight=item.clip_weight,
                )
                for item in record.edit_settings.loras
            ],
        )
    return ImageJobResponse(
        id=record.id,
        status=record.status,
        progress=record.progress,
        phase=record.phase,
        currentStep=record.current_step,
        totalSteps=record.total_steps,
        progressSource=record.progress_source,
        stalled=record.stalled,
        estimatedRemainingSeconds=record.estimated_remaining_seconds,
        prompt=record.prompt,
        settings=ImageJobSettings(
            aspectRatio=record.aspect_ratio,
            style=record.style,
            seed=record.seed,
            provider=record.provider,
            operation=record.operation,
            hasFaceReference=record.face_reference_path is not None,
            sourceJobId=record.source_job_id,
            edit=edit,
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
        "retry_not_available",
        "workflow_missing",
        "workflow_invalid",
        "workflow_bindings_missing",
        "asset_not_deletable",
        "asset_in_use",
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


@router.get("", response_model=ImageJobListResponse)
async def list_image_jobs(
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    job_status: Annotated[ImageJobStatus | None, Query(alias="status")] = None,
    operation: Annotated[ImageJobOperation | None, Query()] = None,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
) -> ImageJobListResponse:
    try:
        records, next_cursor = await service.list_page(
            limit=limit,
            status=job_status,
            operation=operation,
            cursor=cursor,
        )
    except InvalidImageJobCursorError as error:
        raise HTTPException(status_code=422, detail="Image job cursor is invalid.") from error
    return ImageJobListResponse(
        items=[_to_response(record) for record in records],
        nextCursor=next_cursor,
    )


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


@router.post(
    "/{job_id}/retry",
    response_model=ImageJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def retry_image_job(
    job_id: str,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> ImageJobResponse:
    try:
        return _to_response(await service.retry(job_id))
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error


@router.delete("/{job_id}/asset", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image_job_asset(
    job_id: str,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> Response:
    try:
        service.delete_asset(job_id)
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _stored_file_response(request: Request, item: StoredMediaFile) -> Response:
    headers = {
        "Cache-Control": "private, max-age=31536000, immutable",
        "ETag": item.etag,
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == item.etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return FileResponse(
        item.path,
        media_type=item.mime_type,
        filename=None,
        headers=headers,
    )


@router.get("/{job_id}/result", response_class=FileResponse)
async def get_image_job_result(
    job_id: str,
    request: Request,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> Response:
    try:
        item = await service.resolve_result_file(job_id)
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error
    return _stored_file_response(request, item)


@router.get("/{job_id}/thumbnail", response_class=FileResponse)
async def get_image_job_thumbnail(
    job_id: str,
    request: Request,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> Response:
    try:
        item = await service.resolve_result_file(job_id, thumbnail=True)
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error
    return _stored_file_response(request, item)


@router.get("/{job_id}/inputs/{role}", response_class=FileResponse)
async def get_image_job_input(
    job_id: str,
    request: Request,
    role: str,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> Response:
    try:
        item = service.resolve_input_file(job_id, role)
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error
    except ImageProviderError as error:
        raise _provider_unavailable(error) from error
    return _stored_file_response(request, item)


@router.get("/{job_id}/events", response_class=StreamingResponse)
async def stream_image_job(
    job_id: str,
    client_request: Request,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
) -> StreamingResponse:
    try:
        service.repository.get(job_id)
    except ImageJobNotFoundError as error:
        raise _not_found(error) from error

    async def events() -> AsyncIterator[str]:
        previous = ""
        while not await client_request.is_disconnected():
            try:
                record = await service.get(job_id)
            except ImageProviderError:
                break
            payload = _to_response(record).model_dump_json(by_alias=True)
            if payload != previous:
                yield f"event: job\ndata: {payload}\n\n"
                previous = payload
            if record.status in TERMINAL_STATUSES:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
