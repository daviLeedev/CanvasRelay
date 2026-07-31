from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.schemas import ImageJobCreate, ImageJobResponse, ImageJobResult, ImageJobSettings
from app.domain.image_jobs import ImageJobRecord, calculate_state, image_dimensions, render_demo_svg
from app.repositories.image_jobs import ImageJobNotFoundError, ImageJobRepository

router = APIRouter(prefix="/image-jobs", tags=["image jobs"])


def get_image_job_repository(request: Request) -> ImageJobRepository:
    return cast(ImageJobRepository, request.app.state.image_jobs)


def _get_or_404(repository: ImageJobRepository, job_id: str) -> ImageJobRecord:
    try:
        return repository.get(job_id)
    except ImageJobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Image job was not found.") from error


def _to_response(repository: ImageJobRepository, record: ImageJobRecord) -> ImageJobResponse:
    state = calculate_state(record, repository.now())
    result = None
    if state.status == "completed":
        width, height = image_dimensions(record.aspect_ratio)
        result = ImageJobResult(
            url=f"/api/v1/image-jobs/{record.id}/result",
            mimeType="image/svg+xml",
            width=width,
            height=height,
        )
    return ImageJobResponse(
        id=record.id,
        status=state.status,
        progress=state.progress,
        prompt=record.prompt,
        settings=ImageJobSettings(
            aspectRatio=record.aspect_ratio,
            style=record.style,
            seed=record.seed,
        ),
        createdAt=record.created_at,
        startedAt=state.started_at,
        completedAt=state.completed_at,
        result=result,
        error=None,
    )


@router.post("", response_model=ImageJobResponse, status_code=status.HTTP_201_CREATED)
async def create_image_job(
    payload: ImageJobCreate,
    repository: Annotated[ImageJobRepository, Depends(get_image_job_repository)],
) -> ImageJobResponse:
    record = repository.create(
        prompt=payload.prompt,
        aspect_ratio=payload.aspect_ratio,
        style=payload.style,
        seed=payload.seed,
    )
    return _to_response(repository, record)


@router.get("/{job_id}", response_model=ImageJobResponse)
async def get_image_job(
    job_id: str,
    repository: Annotated[ImageJobRepository, Depends(get_image_job_repository)],
) -> ImageJobResponse:
    return _to_response(repository, _get_or_404(repository, job_id))


@router.delete("/{job_id}", response_model=ImageJobResponse)
async def cancel_image_job(
    job_id: str,
    repository: Annotated[ImageJobRepository, Depends(get_image_job_repository)],
) -> ImageJobResponse:
    try:
        record = repository.cancel(job_id)
    except ImageJobNotFoundError as error:
        raise HTTPException(status_code=404, detail="Image job was not found.") from error
    return _to_response(repository, record)


@router.get("/{job_id}/result", response_class=Response)
async def get_image_job_result(
    job_id: str,
    repository: Annotated[ImageJobRepository, Depends(get_image_job_repository)],
) -> Response:
    record = _get_or_404(repository, job_id)
    state = calculate_state(record, repository.now())
    if state.status != "completed":
        raise HTTPException(status_code=409, detail="Image result is not ready.")
    return Response(
        content=render_demo_svg(record),
        media_type="image/svg+xml",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
