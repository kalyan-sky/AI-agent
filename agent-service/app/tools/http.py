"""Shared HTTP helpers for tools that call the mock enterprise API.

GET is idempotent so it gets a bounded retry; POST/PATCH mutate state so
they're retried more conservatively (or not at all for PATCH, matching
the existing ticket-update semantics).
"""

import asyncio

import httpx
import structlog
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import fetch_id_token
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings
from app.testing.failure_injection import should_inject

logger = structlog.get_logger(__name__)


def _maybe_inject(settings: Settings | None, method: str, url: str) -> httpx.Response | None:
    """A synthetic response/exception for the two mock-enterprise failure
    injection targets, or None (no injection) — the caller raises/returns
    whatever this produces. `enterprise_500` returns a real httpx.Response
    (so response.raise_for_status() call sites behave exactly as they
    would for a genuine 500) rather than raising directly.
    """
    if settings is None:
        return None
    if should_inject(settings, "enterprise_timeout"):
        raise httpx.TimeoutException("injected failure: enterprise_timeout")
    if should_inject(settings, "enterprise_500"):
        return httpx.Response(
            status_code=500,
            json={"detail": "injected failure: enterprise_500"},
            request=httpx.Request(method, url),
        )
    return None


async def _auth_headers(audience: str) -> dict[str, str]:
    """A Cloud Run identity token as an Authorization header, or {} —
    when `audience` is unset (the default everywhere except a real GCP
    deployment; see Settings.gcp_id_token_audience), or when a token
    can't be obtained because there's no metadata server to ask (local
    dev, tests, CI). Only that specific "can't get a token" failure is
    swallowed here — a real 401/403 from mock-enterprise itself still
    surfaces normally as an HTTP error response, not from this function.

    fetch_id_token is a blocking call (it's the synchronous google-auth
    library) — run in a thread so it can't stall this async function's
    event loop.
    """
    if not audience:
        return {}
    try:
        token = await asyncio.to_thread(fetch_id_token, GoogleAuthRequest(), audience)
        return {"Authorization": f"Bearer {token}"}
    except DefaultCredentialsError as exc:
        logger.warning("gcp_identity_token_unavailable", audience=audience, error=str(exc))
        return {}


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, max=2),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def get(
    url: str, timeout_s: float, audience: str = "", settings: Settings | None = None
) -> httpx.Response:
    injected = _maybe_inject(settings, "GET", url)
    if injected is not None:
        return injected
    headers = await _auth_headers(audience)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.get(url, headers=headers)


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.2, max=2),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def post(
    url: str,
    json_body: dict,
    timeout_s: float,
    audience: str = "",
    settings: Settings | None = None,
) -> httpx.Response:
    injected = _maybe_inject(settings, "POST", url)
    if injected is not None:
        return injected
    headers = await _auth_headers(audience)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.post(url, json=json_body, headers=headers)


async def patch(
    url: str,
    json_body: dict,
    timeout_s: float,
    audience: str = "",
    settings: Settings | None = None,
) -> httpx.Response:
    injected = _maybe_inject(settings, "PATCH", url)
    if injected is not None:
        return injected
    headers = await _auth_headers(audience)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.patch(url, json=json_body, headers=headers)
