import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.image_jobs import _to_response, get_image_job_service
from app.api.schemas import ImageJobResponse
from app.domain.image_jobs import (
    AspectRatio,
    EditFitMode,
    ImageEditSettings,
    ImageMimeType,
    ImageStyle,
    LoraSelection,
    ProviderContent,
)
from app.providers.base import ImageProviderError
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


def _parse_loras(value: str) -> tuple[LoraSelection, ...]:
    try:
        payload: Any = json.loads(value)
    except json.JSONDecodeError as error:
        raise HTTPException(422, detail="LoRA settings must be valid JSON.") from error
    if not isinstance(payload, list) or len(payload) > 8:
        raise HTTPException(422, detail="Choose no more than eight LoRAs.")
    selections: list[LoraSelection] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            raise HTTPException(422, detail="Each LoRA setting must be an object.")
        identifier = item.get("id")
        model_weight = item.get("modelWeight")
        clip_weight = item.get("clipWeight")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise HTTPException(422, detail="Each selected LoRA must be unique.")
        if not isinstance(model_weight, int | float) or not -3 <= model_weight <= 10:
            raise HTTPException(422, detail="LoRA model weight must be between -3 and 10.")
        if not isinstance(clip_weight, int | float) or not -3 <= clip_weight <= 3:
            raise HTTPException(422, detail="LoRA CLIP weight must be between -3 and 3.")
        seen.add(identifier)
        selections.append(LoraSelection(identifier, float(model_weight), float(clip_weight)))
    return tuple(selections)


@router.post("", response_model=ImageJobResponse, status_code=status.HTTP_201_CREATED)
async def create_image_edit_job(
    service: Annotated[ImageJobService, Depends(get_image_job_service)],
    prompt: Annotated[str, Form(min_length=1, max_length=1200)],
    aspect_ratio: Annotated[AspectRatio, Form(alias="aspectRatio")],
    style: Annotated[ImageStyle, Form()],
    source: Annotated[UploadFile | None, File()] = None,
    source_job_id: Annotated[str | None, Form(alias="sourceJobId")] = None,
    seed: Annotated[int | None, Form(ge=0, le=2_147_483_647)] = None,
    face_reference: Annotated[UploadFile | None, File(alias="faceReference")] = None,
    steps: Annotated[int, Form(ge=4, le=12)] = 8,
    cfg: Annotated[float, Form(ge=0, le=4)] = 1.0,
    reference_influence: Annotated[
        float, Form(alias="referenceInfluence", ge=0, le=10)
    ] = 4.0,
    grounding_resolution: Annotated[
        int, Form(alias="groundingResolution")
    ] = 768,
    fit_mode: Annotated[EditFitMode, Form(alias="fitMode")] = "fit",
    sampler: Annotated[str, Form(min_length=1, max_length=80)] = "euler",
    scheduler: Annotated[str, Form(min_length=1, max_length=80)] = "simple",
    loras: Annotated[str, Form()] = "[]",
) -> ImageJobResponse:
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Prompt must include visible text.",
        )
    normalized_source_job_id = source_job_id.strip() if source_job_id else None
    if (source is None) == (normalized_source_job_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload one source image or choose one completed Library result.",
        )
    if grounding_resolution not in {384, 512, 768, 1024}:
        raise HTTPException(422, detail="Choose a supported grounding resolution.")
    options = await service.describe_edit_options()
    if sampler not in options.samplers or scheduler not in options.schedulers:
        raise HTTPException(422, detail="Choose a sampler and scheduler supported by the provider.")
    selected_loras = _parse_loras(loras)
    allowed_loras = {item.id for item in options.loras}
    if any(item.id not in allowed_loras for item in selected_loras):
        raise HTTPException(422, detail="One or more selected LoRAs are not available.")

    max_bytes = service.max_upload_bytes
    source_content = await _read_image(source, max_bytes) if source is not None else None
    face_content = (
        await _read_image(face_reference, max_bytes)
        if face_reference is not None
        else None
    )
    try:
        record = await service.create_edit(
            prompt=normalized_prompt,
            aspect_ratio=aspect_ratio,
            style=style,
            seed=seed,
            source=source_content,
            source_job_id=normalized_source_job_id,
            face_reference=face_content,
            edit_settings=ImageEditSettings(
                steps=steps,
                cfg=cfg,
                reference_influence=reference_influence,
                grounding_resolution=grounding_resolution,
                fit_mode=fit_mode,
                sampler=sampler,
                scheduler=scheduler,
                loras=selected_loras,
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
