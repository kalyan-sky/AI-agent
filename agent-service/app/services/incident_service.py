"""Ticket/incident retrieval — proxies to the mock enterprise API.

GET is idempotent, so a bounded retry (3 attempts, short exponential
backoff) is safe here; every network call carries an explicit timeout
from Settings. Upstream 404 and unreachable-upstream are distinguished so
the route can map them to the right HTTP status instead of a generic 500.

Uses app.tools.http rather than its own httpx client — that module is
also where a Cloud Run identity token gets attached when
Settings.gcp_id_token_audience is set (see its docstring), and this
service hits the exact same mock-enterprise deployment every tool in
app/tools/ does.
"""

import httpx
import structlog

from app.api.schemas import TicketResponse
from app.config import Settings
from app.tools import http

logger = structlog.get_logger(__name__)


class TicketNotFoundError(Exception):
    pass


class UpstreamUnavailableError(Exception):
    pass


async def get_ticket(ticket_id: str, settings: Settings) -> TicketResponse:
    url = f"{settings.mock_enterprise_base_url}/tickets/{ticket_id}"
    try:
        resp = await http.get(
            url, settings.mock_enterprise_timeout_s, audience=settings.gcp_id_token_audience
        )
    except httpx.TransportError as exc:
        logger.error("ticket_upstream_unreachable", ticket_id=ticket_id, error=str(exc))
        raise UpstreamUnavailableError(str(exc)) from exc

    if resp.status_code == 404:
        raise TicketNotFoundError(ticket_id)
    resp.raise_for_status()
    return TicketResponse(**resp.json())
