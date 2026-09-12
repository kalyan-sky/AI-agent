"""In-memory ticket store.

Minimal slice needed for agent-service's GET /api/v1/tickets/{id} proxy.
The full incident/ticket catalog (create/update, incidents, seedable
failure scenarios) is a later build phase — this only needs to answer
reads for now.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class Ticket(BaseModel):
    ticket_id: str
    title: str
    description: str
    status: str = "open"
    priority: str = "medium"
    service: str | None = None
    created_at: datetime
    updated_at: datetime


_TICKETS: dict[str, Ticket] = {
    "TICKET-1001": Ticket(
        ticket_id="TICKET-1001",
        title="payment-service returning 500s in production",
        description=(
            "payment-service deployment rollout has 1/3 replicas available; "
            "checkout requests intermittently failing with 500 errors."
        ),
        status="open",
        priority="high",
        service="payment-service",
        created_at=datetime(2026, 9, 10, 14, 32, tzinfo=UTC),
        updated_at=datetime(2026, 9, 10, 14, 32, tzinfo=UTC),
    ),
}


@router.get("/tickets/{ticket_id}", response_model=Ticket)
async def get_ticket(ticket_id: str) -> Ticket:
    ticket = _TICKETS.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket
