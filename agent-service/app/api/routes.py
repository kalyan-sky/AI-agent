"""Top-level API routes.

Route handlers stay thin: validate input, delegate to `app.services.*`,
return a schema. `/health`, `/ready`, and `/metrics` never require auth
(they're probed by orchestrators/load balancers and scraped by
Prometheus); every other endpoint requires at least `viewer`.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.dependencies import (
    check_mock_enterprise,
    check_postgres,
    check_qdrant,
    check_redis,
)
from app.api.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    ApprovalDecisionRequest,
    ApprovalResponse,
    HealthResponse,
    RagSearchRequest,
    RagSearchResponse,
    ReadinessResponse,
    TicketResponse,
)
from app.config import Settings, get_settings
from app.database.models import Approval
from app.security.authorization import Role, require_role
from app.security.rate_limit import enforce_rate_limit
from app.services import agent_service, approval_service, incident_service, rag_service

router = APIRouter()


@router.get("/metrics", tags=["system"])
async def metrics() -> Response:
    """Prometheus scrape target. Unauthenticated like /health and /ready —
    see app/observability/metrics.py for why."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
    # Rate-limited (unlike the other routes below) because every call here
    # spends real LLM tokens — the one endpoint where unbounded retries or
    # a runaway caller directly costs money, not just CPU.
    dependencies=[Depends(require_role(Role.viewer)), Depends(enforce_rate_limit)],
)
async def run_agent(
    body: AgentRunRequest, settings: Settings = Depends(get_settings)
) -> AgentRunResponse:
    return await agent_service.run(body, settings)


@router.post(
    "/api/v1/rag/search",
    response_model=RagSearchResponse,
    tags=["rag"],
    dependencies=[Depends(require_role(Role.viewer)), Depends(enforce_rate_limit)],
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
async def get_ticket(ticket_id: str, settings: Settings = Depends(get_settings)) -> TicketResponse:
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


@router.get(
    "/api/v1/approvals",
    response_model=list[ApprovalResponse],
    tags=["approvals"],
    dependencies=[Depends(require_role(Role.operator))],
)
async def list_approvals(settings: Settings = Depends(get_settings)) -> list[ApprovalResponse]:
    approvals = await approval_service.list_pending(settings)
    return [_to_approval_response(a) for a in approvals]


@router.post(
    "/api/v1/approvals/{approval_id}/decision",
    response_model=ApprovalResponse,
    tags=["approvals"],
)
async def decide_approval(
    approval_id: int,
    body: ApprovalDecisionRequest,
    principal=Depends(require_role(Role.operator)),
    settings: Settings = Depends(get_settings),
) -> ApprovalResponse:
    try:
        approval = await approval_service.decide(
            approval_id,
            body.decision,
            decided_by=principal.role.name,
            reason=body.reason,
            settings=settings,
        )
    except approval_service.ApprovalNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval {approval_id} not found"
        ) from exc
    except approval_service.ApprovalAlreadyDecidedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Approval {approval_id} already decided: {exc.current_status}",
        ) from exc
    return _to_approval_response(approval)


def _to_approval_response(approval: Approval) -> ApprovalResponse:
    return ApprovalResponse(
        id=approval.id,
        tool_execution_id=approval.tool_execution_id,
        tool_name=approval.tool_execution.tool_name,
        arguments=approval.tool_execution.arguments,
        risk_tier=approval.tool_execution.risk_tier,
        status=approval.status,
        tool_execution_status=approval.tool_execution.status,
        requested_at=approval.requested_at,
        decided_at=approval.decided_at,
        decided_by=approval.decided_by,
        reason=approval.reason,
    )
