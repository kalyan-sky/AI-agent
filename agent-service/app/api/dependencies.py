"""Shared FastAPI dependencies: correlation IDs and readiness probes.

Readiness probes are intentionally lightweight, direct connection checks
(no ORM, no connection pool reuse) so `/ready` reflects real reachability
of each dependency rather than the health of an internal pool.
"""
import time
import uuid
from contextvars import ContextVar

import asyncpg
import httpx
import redis.asyncio as aioredis
from fastapi import Request

from app.api.schemas import ComponentStatus
from app.config import Settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_or_create_request_id(request: Request) -> str:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request_id_ctx.set(request_id)
    return request_id


async def check_postgres(settings: Settings) -> ComponentStatus:
    start = time.perf_counter()
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conn = await asyncpg.connect(dsn, timeout=3)
        await conn.execute("SELECT 1")
        await conn.close()
        return ComponentStatus(
            name="postgres", status="ok", latency_ms=_ms(start)
        )
    except Exception as exc:  # noqa: BLE001 - readiness probe must never raise
        return ComponentStatus(
            name="postgres", status="down", detail=str(exc), latency_ms=_ms(start)
        )


async def check_redis(settings: Settings) -> ComponentStatus:
    start = time.perf_counter()
    client = aioredis.from_url(settings.redis_url, socket_timeout=3)
    try:
        await client.ping()
        return ComponentStatus(name="redis", status="ok", latency_ms=_ms(start))
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(
            name="redis", status="down", detail=str(exc), latency_ms=_ms(start)
        )
    finally:
        await client.aclose()


async def check_qdrant(settings: Settings) -> ComponentStatus:
    start = time.perf_counter()
    if settings.qdrant_local_path:
        return ComponentStatus(
            name="qdrant", status="ok", detail="embedded local-mode", latency_ms=0.0
        )
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.qdrant_url}/readyz")
            resp.raise_for_status()
        return ComponentStatus(name="qdrant", status="ok", latency_ms=_ms(start))
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(
            name="qdrant", status="down", detail=str(exc), latency_ms=_ms(start)
        )


async def check_mock_enterprise(settings: Settings) -> ComponentStatus:
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.mock_enterprise_base_url}/health")
            resp.raise_for_status()
        return ComponentStatus(name="mock_enterprise", status="ok", latency_ms=_ms(start))
    except Exception as exc:  # noqa: BLE001
        return ComponentStatus(
            name="mock_enterprise", status="down", detail=str(exc), latency_ms=_ms(start)
        )


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
