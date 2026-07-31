from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.image_jobs import router as image_jobs_router
from app.api.providers import router as providers_router
from app.core.config import Settings, get_settings
from app.providers.base import ImageGenerationProvider
from app.providers.comfyui import ComfyUIImageProvider
from app.providers.demo import DemoImageProvider
from app.repositories.image_jobs import ImageJobRepository
from app.services.image_jobs import ImageJobService


def build_image_provider(settings: Settings) -> ImageGenerationProvider:
    if settings.active_image_provider == "comfyui":
        return ComfyUIImageProvider(
            base_url=settings.comfyui_base_url,
            workflow_path=settings.resolved_comfyui_workflow_path,
            output_node_id=settings.comfyui_output_node_id,
            timeout_seconds=settings.comfyui_timeout_seconds,
            max_result_bytes=settings.comfyui_max_result_bytes,
        )
    return DemoImageProvider()


def create_app(
    settings: Settings | None = None,
    image_jobs: ImageJobRepository | None = None,
    image_provider: ImageGenerationProvider | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    repository = image_jobs or ImageJobRepository()
    provider = image_provider or build_image_provider(app_settings)
    application = FastAPI(
        title="CanvasRelay API",
        version=app_settings.app_version,
        description="Public orchestration API for the CanvasRelay studio.",
    )
    application.state.settings = app_settings
    application.state.image_jobs = repository
    application.state.image_job_service = ImageJobService(repository, provider)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["DELETE", "GET", "OPTIONS", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(providers_router, prefix="/api/v1")
    application.include_router(image_jobs_router, prefix="/api/v1")
    return application


app = create_app()
