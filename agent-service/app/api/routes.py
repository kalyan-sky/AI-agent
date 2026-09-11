"""Top-level API routes.

Route handlers stay thin: validate input, delegate to `app.services.*`,
return a schema. `/health` and `/ready` are the two Phase 1 endpoints;
agent/RAG/ticket endpoints are added in Phase 2.
"""
import asyncio

from fastapi import APIRouter, Depends

from app.api.dependencies import (
    check_mock_enterprise,
    check_postgres,
    check_qdrant,
    check_redis,
)
from app.api.schemas import HealthResponse, ReadinessResponse
from app.config import Settings, get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness probe — process is up. Does not check downstream dependencies."""
    return HealthResponse(service=settings.service_name)


@router.get("/ready", response_model=ReadinessResponse, tags=["system"])
async def ready(settings: Settings = Depends(get_settings)) -> ReadinessResponse:
    """Readiness probe — checks every downstream dependency in parallel."""
    components = await asyncio.gather(
        check_postgres(settings),
        check_redis(settings),
        check_qdrant(settings),
        check_mock_enterprise(settings),
    )
    overall = "ready" if all(c.status == "ok" for c in components) else "not_ready"
    return ReadinessResponse(status=overall, components=list(components))
