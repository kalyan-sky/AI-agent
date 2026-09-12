"""Ticket and incident tools — wrap mock-enterprise's tickets/incidents API.

get_ticket is READ_ONLY. create_ticket/update_ticket/create_incident are
LOW_RISK: they write data, but only within this mock enterprise system
(no production system access), are fully reversible (an unwanted ticket
can just be closed), and are always logged — so auto-execution under
policy is an acceptable default, unlike a real production-impacting
action (see rollback/restart, which stay HIGH_RISK/CRITICAL and are
introduced with the human-approval workflow).
"""

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.agent.policies import RiskTier
from app.config import Settings
from app.tools.base import Tool, ToolError
from app.tools.health import _get


class GetTicketInput(BaseModel):
    ticket_id: str = Field(..., min_length=1, max_length=50)


class GetTicketTool(Tool[GetTicketInput]):
    name = "get_ticket"
    description = "Get a ticket by ID."
    input_schema = GetTicketInput
    risk_tier = RiskTier.READ_ONLY
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: GetTicketInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/tickets/{args.ticket_id}"
        try:
            resp = await _get(url, self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        if resp.status_code == 404:
            raise ToolError(f"ticket {args.ticket_id} not found")
        resp.raise_for_status()
        return resp.json()


class CreateTicketInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=4000)
    priority: str = Field(default="medium")
    service: str | None = None


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.2, max=2),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def _post(url: str, json_body: dict, timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.post(url, json=json_body)


async def _patch(url: str, json_body: dict, timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.patch(url, json=json_body)


class CreateTicketTool(Tool[CreateTicketInput]):
    name = "create_ticket"
    description = "Create a ticket. Args: title, description, priority (low|medium|high), service."
    input_schema = CreateTicketInput
    risk_tier = RiskTier.LOW_RISK
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: CreateTicketInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/tickets"
        try:
            resp = await _post(url, args.model_dump(), self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        resp.raise_for_status()
        return resp.json()


class UpdateTicketInput(BaseModel):
    ticket_id: str = Field(..., min_length=1, max_length=50)
    status: str = Field(..., min_length=1, max_length=30)


class UpdateTicketTool(Tool[UpdateTicketInput]):
    name = "update_ticket"
    description = (
        "Update a ticket's status. Args: ticket_id, status (e.g. open|in_progress|resolved)."
    )
    input_schema = UpdateTicketInput
    risk_tier = RiskTier.LOW_RISK
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: UpdateTicketInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/tickets/{args.ticket_id}"
        try:
            resp = await _patch(url, {"status": args.status}, self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        if resp.status_code == 404:
            raise ToolError(f"ticket {args.ticket_id} not found")
        resp.raise_for_status()
        return resp.json()


class CreateIncidentInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    service: str = Field(..., min_length=1, max_length=100)
    severity: str = Field(default="medium")
    description: str = Field(default="")


class CreateIncidentTool(Tool[CreateIncidentInput]):
    name = "create_incident"
    description = (
        "Create an incident record. Args: title, service, severity (low|medium|high), description."
    )
    input_schema = CreateIncidentInput
    risk_tier = RiskTier.LOW_RISK
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: CreateIncidentInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/incidents"
        try:
            resp = await _post(url, args.model_dump(), self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        resp.raise_for_status()
        return resp.json()
