from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.api.image_edits import _read_image
from app.api.image_jobs import _to_response, get_image_job_service
from app.api.schemas import ImageJobResponse
from app.domain.image_jobs import AspectRatio, GPTImageSettings, ImageStyle, ProviderContent
from app.providers.base import ImageProviderError
from app.services.gpt_access import GPTAccessGuard
from app.services.image_jobs import ImageJobService

router = APIRouter(prefix="/gpt-image-jobs", tags=["owner gpt image jobs"])


def get_gpt_access_guard(request: Request) -> GPTAccessGuard:
    return cast(GPTAccessGuard, request.app.state.gpt_access_guard)


@router.post("", response_model=ImageJobResponse, status_code=status.HTTP_201_CREATED)
async def create_gpt_image_job(
    request: Request,
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
    guard: Annotated[GPTAccessGuard, Depends(get_gpt_access_guard)],
    prompt: Annotated[str, Form(min_length=1, max_length=1200)],
    aspect_ratio: Annotated[AspectRatio, Form(alias="aspectRatio")],
    style: Annotated[ImageStyle, Form()],
    mode: Annotated[Literal["generate", "edit"], Form()] = "generate",
    references: Annotated[list[UploadFile] | None, File(alias="references")] = None,
    seed: Annotated[int | None, Form(ge=0, le=2_147_483_647)] = None,
    quality: Annotated[Literal["auto", "low", "medium", "high"], Form()] = "auto",
    size: Annotated[
        Literal["1024x1024", "1024x1536", "1536x1024"], Form()
    ] = "1024x1024",
    count: Annotated[int, Form(ge=1, le=2)] = 1,
    moderation: Annotated[Literal["auto", "low"], Form()] = "auto",
    reasoning_effort: Annotated[
        Literal["none", "low", "medium", "high"], Form(alias="reasoningEffort")
    ] = "none",
    web_search: Annotated[bool, Form(alias="webSearch")] = False,
) -> ImageJobResponse:
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise HTTPException(422, detail="Prompt must include visible text.")
    uploads = references or []
    if len(uploads) > 5:
        raise HTTPException(422, detail="Choose no more than five reference images.")
    if mode == "edit" and not uploads:
        raise HTTPException(422, detail="Add one to five reference images for an image edit.")
    contents: list[ProviderContent] = []
    for upload in uploads:
        contents.append(await _read_image(upload, service.max_upload_bytes))
    guard.authorize(request)
    try:
        record = await service.create_gpt(
            prompt=normalized_prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=seed,
            operation=mode,
            references=tuple(contents),
            gpt_settings=GPTImageSettings(
                quality=quality,
                size=size,
                count=count,
                moderation=moderation,
                reasoning_effort=reasoning_effort,
                web_search=web_search,
            ),
        )
    except ImageProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": error.details.code,
                "message": error.details.message,
                "action": error.details.action,
            },
        ) from error
    return _to_response(record)
