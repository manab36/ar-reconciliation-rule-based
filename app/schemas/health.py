from typing import Literal

from pydantic import Field

from app.schemas.api_base import APIBaseResponse


class HealthResponse(APIBaseResponse):
    status: Literal["healthy", "unhealthy"] = Field(description="Health status")
    version: str = Field(description="API version")
    timestamp: str = Field(description="Current timestamp (ISO format)")
    services: dict[str, str] = Field(
        default_factory=dict, description="Status of dependent services"
    )


class LivenessCheck(APIBaseResponse):
    status: Literal["alive"] = Field(default="alive", description="Liveness status")


class ReadinessCheck(APIBaseResponse):
    status: Literal["ready", "not_ready"] = Field(description="Readiness status")
    details: dict[str, str] = Field(
        default_factory=dict, description="Dependency readiness details"
    )


class StartupCheck(APIBaseResponse):
    status: Literal["started", "not_started"] = Field(description="Startup status")
    initialized: bool = Field(description="Whether initialization is complete")


class HealthCheckResponse(APIBaseResponse):
    liveness: LivenessCheck
    readiness: ReadinessCheck
    startup: StartupCheck
    version: str
    timestamp: str
    services: dict[str, str] = Field(default_factory=dict)
