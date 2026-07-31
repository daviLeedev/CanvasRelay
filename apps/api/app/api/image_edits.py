from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.image_jobs import _to_response, get_image_job_service
from app.api.schemas import ImageJobResponse
from app.domain.image_jobs import AspectRatio, ImageMimeType, ImageStyle, ProviderContent
from app.services.image_jobs import ImageJobService

router = APIRouter(prefix="/image-edit-jobs", tags=["image edit jobs"])


def _image_mime_type(body: bytes) -> ImageMimeType | None:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _read_image(upload: UploadFile, max_bytes: int) -> ProviderContent:
    try:
        body = await upload.read(max_bytes + 1)
    finally:
        await upload.close()
    if len(body) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The selected image is larger than the configured upload limit.",
        )
    mime_type = _image_mime_type(body)
    if mime_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a valid PNG, JPEG, or WebP image.",
        )
    return ProviderContent(body, mime_type)


@router.post("", response_model=ImageJobResponse, status_code=status.HTTP_201_CREATED)
async def create_image_edit_job(
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
    prompt: Annotated[str, Form(min_length=1, max_length=1200)],
    aspect_ratio: Annotated[AspectRatio, Form(alias="aspectRatio")],
    style: Annotated[ImageStyle, Form()],
    source: Annotated[UploadFile, File()],
    seed: Annotated[int | None, Form(ge=0, le=2_147_483_647)] = None,
    face_reference: Annotated[UploadFile | None, File(alias="faceReference")] = None,
) -> ImageJobResponse:
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Prompt must include visible text.",
        )
    max_bytes = service.max_upload_bytes
    source_content = await _read_image(source, max_bytes)
    face_content = (
        await _read_image(face_reference, max_bytes)
        if face_reference is not None
        else None
    )
    record = await service.create_edit(
        prompt=normalized_prompt,
        aspect_ratio=aspect_ratio,
        style=style,
        seed=seed,
        source=source_content,
        face_reference=face_content,
    )
    return _to_response(record)
