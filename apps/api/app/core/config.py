from functools import lru_cache
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
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    app_version: str = "0.1.0"

    @property
    def allowed_origins(self) -> list[str]:
        return [
            normalized
            for origin in self.cors_origins.split(",")
            if (normalized := origin.strip().rstrip("/"))
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_request_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
