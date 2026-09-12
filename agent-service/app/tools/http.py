"""Shared HTTP helpers for tools that call the mock enterprise API.

GET is idempotent so it gets a bounded retry; POST/PATCH mutate state so
they're retried more conservatively (or not at all for PATCH, matching
the existing ticket-update semantics).
"""

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, max=2),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def get(url: str, timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.get(url)


@retry(
    reraise=True,
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.2, max=2),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def post(url: str, json_body: dict, timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.post(url, json=json_body)


async def patch(url: str, json_body: dict, timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.patch(url, json=json_body)
