"""In-memory ticket store: GET/POST/PATCH /tickets."""
from datetime import UTC, datetime
from itertools import count

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_ticket_sequence = count(1002)


class TicketCreate(BaseModel):
    title: str
    description: str
    priority: str = "medium"
    service: str | None = None


class TicketUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None


class Ticket(TicketCreate):
    ticket_id: str
    status: str = "open"
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


@router.post("/tickets", response_model=Ticket, status_code=201)
async def create_ticket(body: TicketCreate) -> Ticket:
    now = datetime.now(UTC)
    ticket_id = f"TICKET-{next(_ticket_sequence)}"
    ticket = Ticket(ticket_id=ticket_id, created_at=now, updated_at=now, **body.model_dump())
    _TICKETS[ticket_id] = ticket
    return ticket


@router.patch("/tickets/{ticket_id}", response_model=Ticket)
async def update_ticket(ticket_id: str, body: TicketUpdate) -> Ticket:
    ticket = _TICKETS.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    updates = body.model_dump(exclude_unset=True)
    updated = ticket.model_copy(update={**updates, "updated_at": datetime.now(UTC)})
    _TICKETS[ticket_id] = updated
    return updated
