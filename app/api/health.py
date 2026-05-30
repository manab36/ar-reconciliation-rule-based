"""Health check API routes."""
from __future__ import annotations


from __future__ import annotations
from app.core.config import settings
from datetime import datetime
import pytz
from fastapi import APIRouter, Query
from app.schemas.health import HealthResponse, LivenessCheck, ReadinessCheck, StartupCheck, HealthCheckResponse

router = APIRouter()



def get_version() -> str:
    return settings.API_VERSION

def get_timestamp() -> str:
    tz = pytz.timezone(settings.TIMEZONE)
    return datetime.now(tz).isoformat()

def check_services() -> dict[str, str]:
    # TODO: Implement real dependency checks (DB, cache, etc.)
    return {"database": "ok"}



@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Main health check endpoint for backwards compatibility.
    Returns basic health information compatible with existing HealthResponse model.
    """
    return HealthResponse(
        status="healthy",
        version=get_version(),
        timestamp=get_timestamp(),
        services=check_services(),
    )


@router.get("/liveness", response_model=LivenessCheck)
async def liveness_check() -> LivenessCheck:
    """
    Liveness check - is the app running?
    """
    return LivenessCheck()


@router.get("/readiness", response_model=ReadinessCheck)
async def readiness_check() -> ReadinessCheck:
    """
    Readiness check - is it ready to serve traffic?
    Checks external dependencies like database and cache.
    """
    # TODO: Implement real dependency checks (DB, cache, etc.)
    return ReadinessCheck(status="ready", details=check_services())


@router.get("/startup", response_model=StartupCheck)
async def startup_check() -> StartupCheck:
    """
    Startup check - has it initialized properly?
    """
    # TODO: Implement real startup checks
    return StartupCheck(status="started", initialized=True)


@router.get("/detailed", response_model=HealthCheckResponse)
async def detailed_health_check(include_details: bool = Query(True, description="Include detailed check results")) -> HealthCheckResponse:
    """
    Comprehensive health check with detailed information.
    Includes all health check types (liveness, readiness, startup).
    """
    liveness = LivenessCheck()
    readiness = ReadinessCheck(status="ready", details=check_services() if include_details else {})
    startup = StartupCheck(status="started", initialized=True)
    return HealthCheckResponse(
        liveness=liveness,
        readiness=readiness,
        startup=startup,
        version=get_version(),
        timestamp=get_timestamp(),
        services=check_services() if include_details else {},
    )
