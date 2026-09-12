"""Ticket/incident retrieval — proxies to the mock enterprise API.

GET is idempotent, so a bounded retry (3 attempts, short exponential
backoff) is safe here; every network call carries an explicit timeout
from Settings. Upstream 404 and unreachable-upstream are distinguished so
the route can map them to the right HTTP status instead of a generic 500.
"""
import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.api.schemas import TicketResponse
from app.config import Settings

logger = structlog.get_logger(__name__)


class TicketNotFoundError(Exception):
    pass


class UpstreamUnavailableError(Exception):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, max=2),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def _get(url: str, timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.get(url)


async def get_ticket(ticket_id: str, settings: Settings) -> TicketResponse:
    url = f"{settings.mock_enterprise_base_url}/tickets/{ticket_id}"
    try:
        resp = await _get(url, settings.mock_enterprise_timeout_s)
    except httpx.TransportError as exc:
        logger.error("ticket_upstream_unreachable", ticket_id=ticket_id, error=str(exc))
        raise UpstreamUnavailableError(str(exc)) from exc

    if resp.status_code == 404:
        raise TicketNotFoundError(ticket_id)
    resp.raise_for_status()
    return TicketResponse(**resp.json())
