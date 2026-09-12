"""Top-level API routes.

Route handlers stay thin: validate input, delegate to `app.services.*`,
return a schema. `/health` and `/ready` never require auth (they're
probed by orchestrators/load balancers); every other endpoint requires at
least `viewer`.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    check_mock_enterprise,
    check_postgres,
    check_qdrant,
    check_redis,
)
from app.api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    HealthResponse,
    RagSearchRequest,
    RagSearchResponse,
    ReadinessResponse,
    TicketResponse,
)
from app.config import Settings, get_settings
from app.security.authorization import Role, require_role
from app.services import agent_service, incident_service, rag_service

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


@router.post(
    "/api/v1/agent/run",
    response_model=AgentRunResponse,
    tags=["agent"],
    dependencies=[Depends(require_role(Role.viewer))],
)
async def run_agent(body: AgentRunRequest) -> AgentRunResponse:
    return await agent_service.run(body)


@router.post(
    "/api/v1/rag/search",
    response_model=RagSearchResponse,
    tags=["rag"],
    dependencies=[Depends(require_role(Role.viewer))],
)
async def search_rag(
    body: RagSearchRequest, settings: Settings = Depends(get_settings)
) -> RagSearchResponse:
    return await rag_service.search(body, settings)


@router.get(
    "/api/v1/tickets/{ticket_id}",
    response_model=TicketResponse,
    tags=["tickets"],
    dependencies=[Depends(require_role(Role.viewer))],
)
async def get_ticket(
    ticket_id: str, settings: Settings = Depends(get_settings)
) -> TicketResponse:
    try:
        return await incident_service.get_ticket(ticket_id, settings)
    except incident_service.TicketNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Ticket {ticket_id} not found"
        ) from exc
    except incident_service.UpstreamUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mock enterprise API unavailable",
        ) from exc
