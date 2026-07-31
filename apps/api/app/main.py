from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.image_jobs import router as image_jobs_router
from app.core.config import Settings, get_settings
from app.repositories.image_jobs import ImageJobRepository


def create_app(
    settings: Settings | None = None,
    image_jobs: ImageJobRepository | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title="CanvasRelay API",
        version=app_settings.app_version,
        description="Public API foundation for the CanvasRelay studio.",
    )
    application.state.settings = app_settings
    application.state.image_jobs = image_jobs or ImageJobRepository()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["DELETE", "GET", "OPTIONS", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(image_jobs_router, prefix="/api/v1")
    return application


app = create_app()
