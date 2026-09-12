"""In-memory incident store: GET/POST /incidents."""
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class IncidentCreate(BaseModel):
    title: str
    service: str
    severity: str = "medium"
    description: str = ""


class Incident(IncidentCreate):
    incident_id: str
    status: str = "open"
    created_at: datetime
    updated_at: datetime


_INCIDENTS: dict[str, Incident] = {}


@router.get("/incidents", response_model=list[Incident])
async def list_incidents() -> list[Incident]:
    return list(_INCIDENTS.values())


@router.post("/incidents", response_model=Incident, status_code=201)
async def create_incident(body: IncidentCreate) -> Incident:
    now = datetime.now(UTC)
    incident = Incident(
        incident_id=f"INC-{uuid4().hex[:8]}",
        created_at=now,
        updated_at=now,
        **body.model_dump(),
    )
    _INCIDENTS[incident.incident_id] = incident
    return incident
