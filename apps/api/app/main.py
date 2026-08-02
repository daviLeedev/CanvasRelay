from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.codex_connection import router as codex_connection_router
from app.api.gpt_images import router as gpt_images_router
from app.api.health import router as health_router
from app.api.image_edits import router as image_edits_router
from app.api.image_jobs import router as image_jobs_router
from app.api.providers import router as providers_router
from app.core.config import Settings, get_settings
from app.providers.base import ImageGenerationProvider
from app.providers.codex_connection import CodexConnectionManager
from app.providers.comfyui import ComfyUIImageProvider
from app.providers.demo import DemoImageProvider
from app.providers.openai_oauth import OpenAIOAuthImageProvider
from app.repositories.image_jobs import ImageJobRepository
from app.repositories.media import FilesystemMediaStore, FilesystemUploadStore
from app.services.gpt_access import GPTAccessGuard
from app.services.image_jobs import ImageJobService


def build_image_provider(settings: Settings) -> ImageGenerationProvider:
    if settings.active_image_provider == "comfyui":
        return ComfyUIImageProvider(
            base_url=settings.comfyui_base_url,
            workflow_path=settings.resolved_comfyui_workflow_path,
            edit_workflow_path=settings.resolved_comfyui_edit_workflow_path,
            edit_face_workflow_path=settings.resolved_comfyui_edit_face_workflow_path,
            edit_lora_allowlist_path=settings.resolved_comfyui_edit_lora_allowlist_path,
            output_node_id=settings.comfyui_output_node_id,
            timeout_seconds=settings.comfyui_timeout_seconds,
            max_result_bytes=settings.comfyui_max_result_bytes,
            stalled_after_seconds=settings.comfyui_stalled_after_seconds,
        )
    return DemoImageProvider()


def create_app(
    settings: Settings | None = None,
    image_jobs: ImageJobRepository | None = None,
    image_provider: ImageGenerationProvider | None = None,
    codex_connection: CodexConnectionManager | None = None,
    gpt_image_provider: ImageGenerationProvider | None = None,
    media_store: FilesystemMediaStore | None = None,
    upload_store: FilesystemUploadStore | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    owns_repository = image_jobs is None
    repository = image_jobs or ImageJobRepository(
        database_url=app_settings.resolved_database_url,
        create_schema=app_settings.resolved_database_url.startswith("sqlite"),
        pool_size=app_settings.database_pool_size,
        max_overflow=app_settings.database_max_overflow,
    )
    provider = image_provider or build_image_provider(app_settings)
    connection = codex_connection or CodexConnectionManager(
        enabled=app_settings.codex_oauth_enabled,
        port=app_settings.codex_oauth_proxy_port,
        proxy_command=app_settings.resolved_codex_oauth_proxy_command,
    )
    oauth_provider = gpt_image_provider or OpenAIOAuthImageProvider(
        connection,
        timeout_seconds=app_settings.codex_oauth_timeout_seconds,
        max_parallel_jobs=app_settings.codex_oauth_parallel_jobs,
        configured_model=app_settings.codex_oauth_model,
    )
    result_store = media_store or FilesystemMediaStore(
        app_settings.media_root,
        app_settings.thumbnail_root,
    )
    source_store = upload_store or FilesystemUploadStore(app_settings.upload_root)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await connection.aclose()
        if owns_repository:
            repository.close()

    application = FastAPI(
        title="CanvasRelay API",
        version=app_settings.app_version,
        description="Public orchestration API for the CanvasRelay studio.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.image_jobs = repository
    application.state.codex_connection = connection
    application.state.gpt_access_guard = GPTAccessGuard(
        global_daily_limit=app_settings.codex_oauth_daily_job_limit,
        ip_daily_limit=app_settings.codex_oauth_ip_daily_job_limit,
        allow_remote_generation=app_settings.codex_oauth_allow_remote_generation,
        allow_docker_gateway=app_settings.codex_oauth_allow_docker_gateway,
    )
    application.state.image_job_service = ImageJobService(
        repository,
        provider,
        result_store,
        source_store,
        app_settings.max_upload_bytes,
        providers={"openai_oauth": oauth_provider},
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["DELETE", "GET", "OPTIONS", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(providers_router, prefix="/api/v1")
    application.include_router(codex_connection_router, prefix="/api/v1")
    application.include_router(image_jobs_router, prefix="/api/v1")
    application.include_router(image_edits_router, prefix="/api/v1")
    application.include_router(gpt_images_router, prefix="/api/v1")
    return application


app = create_app()
