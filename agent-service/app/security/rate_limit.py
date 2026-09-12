"""Redis-backed rate limiting for the LLM/embedding-calling endpoints.

Fixed-window counter per API key: one INCR (+EXPIRE on the first hit in a
window) per request. Deliberately fails OPEN — logs a warning and lets the
request through — if Redis itself is unreachable. Rate limiting protects
availability and cost, not authorization; taking the whole API down
because its own rate-limit backing store is briefly down would be a worse
outcome than a temporarily-unenforced limit. Creates a short-lived client
per call rather than caching one, matching app/api/dependencies.py's
check_redis — a cached client would outlive the event loop of whichever
request created it once pytest-asyncio (or any per-task loop) is in play.
"""

import time

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, status

from app.config import Settings, get_settings
from app.security.api_key import Principal, get_current_principal

logger = structlog.get_logger(__name__)


async def enforce_rate_limit(
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> None:
    client = None
    try:
        client = aioredis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        window = int(time.time()) // settings.rate_limit_window_s
        key = f"ratelimit:{principal.api_key}:{window}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, settings.rate_limit_window_s)
    except Exception as exc:  # noqa: BLE001 - fail open, see module docstring
        logger.warning("rate_limit_backend_unavailable", error=str(exc))
        return
    finally:
        if client is not None:
            await client.aclose()

    if count > settings.rate_limit_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: {settings.rate_limit_requests} requests "
                f"per {settings.rate_limit_window_s}s"
            ),
            headers={"Retry-After": str(settings.rate_limit_window_s)},
        )
