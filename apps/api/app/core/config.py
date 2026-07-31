from functools import lru_cache
from pathlib import Path
from typing import Literal, cast

from fastapi import Request
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CANVASRELAY_",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True
    image_provider: Literal["demo", "comfyui"] | None = None
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_workflow_path: Path | None = None
    comfyui_output_node_id: str | None = None
    comfyui_timeout_seconds: float = 30
    comfyui_max_result_bytes: int = 50 * 1024 * 1024
    data_dir: Path = Path(".canvasrelay")
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    app_version: str = "0.1.0"

    @property
    def allowed_origins(self) -> list[str]:
        return [
            normalized
            for origin in self.cors_origins.split(",")
            if (normalized := origin.strip().rstrip("/"))
        ]

    @property
    def active_image_provider(self) -> Literal["demo", "comfyui"]:
        return self.image_provider or ("demo" if self.demo_mode else "comfyui")

    @property
    def resolved_comfyui_workflow_path(self) -> Path | None:
        path = self.comfyui_workflow_path
        if path is None or path.is_absolute():
            return path
        repository_root = Path(__file__).resolve().parents[4]
        return repository_root / path

    @property
    def resolved_data_dir(self) -> Path:
        if self.data_dir.is_absolute():
            return self.data_dir
        repository_root = Path(__file__).resolve().parents[4]
        return repository_root / self.data_dir

    @property
    def database_path(self) -> Path:
        return self.resolved_data_dir / "canvasrelay.sqlite3"

    @property
    def media_root(self) -> Path:
        return self.resolved_data_dir / "media" / "images"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_request_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
