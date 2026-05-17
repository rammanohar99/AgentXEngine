"""
Health check endpoints.

/health       — liveness probe (is the process running?)
/health/ready — readiness probe (are all dependencies reachable?)

Kubernetes and Cloud Run use these to determine if traffic should be routed.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import check_database_connection
from app.core.redis import check_redis_connection
from app.schemas.common import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def liveness() -> HealthStatus:
    """Liveness probe — always returns 200 if the process is alive."""
    settings = get_settings()
    return HealthStatus(
        status="ok",
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """
    Readiness probe — checks all critical dependencies.
    Returns 200 if ready, 503 if any dependency is down.
    """
    settings = get_settings()

    db_ok = await check_database_connection()
    redis_ok = await check_redis_connection()

    checks = {"database": db_ok, "redis": redis_ok}
    all_healthy = all(checks.values())

    status = HealthStatus(
        status="ready" if all_healthy else "degraded",
        version=settings.app_version,
        environment=settings.environment,
        checks=checks,
    )

    return JSONResponse(
        content=status.model_dump(mode="json"),
        status_code=200 if all_healthy else 503,
    )
