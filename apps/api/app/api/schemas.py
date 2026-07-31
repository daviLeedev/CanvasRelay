from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["ok"]
    service: Literal["canvasrelay-api"]
    version: str
    demo_mode: bool = Field(alias="demoMode")
    timestamp: datetime
