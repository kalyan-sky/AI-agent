"""Rate limiting on the LLM/embedding-calling endpoints.

Uses the real local Redis this sandbox already runs for everything else
(see tests/conftest.py's TEST_DATABASE_URL for the equivalent Postgres
story) — flushing the specific keys these tests touch rather than the
whole instance, since other tests/processes may share it.
"""

from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as aioredis

from app.api.schemas import AgentRunResponse
from app.config import get_settings

REDIS_URL = get_settings().redis_url


async def _flush_rate_limit_keys(api_key: str) -> None:
    client = aioredis.from_url(REDIS_URL)
    try:
        async for key in client.scan_iter(match=f"ratelimit:{api_key}:*"):
            await client.delete(key)
    finally:
        await client.aclose()


@pytest.fixture(autouse=True)
async def _clean_rate_limit_state(viewer_headers):
    api_key = viewer_headers["Authorization"].removeprefix("Bearer ")
    await _flush_rate_limit_keys(api_key)
    yield
    await _flush_rate_limit_keys(api_key)


@pytest.mark.asyncio
async def test_requests_within_budget_are_allowed(client, viewer_headers):
    canned = AgentRunResponse(conversation_id="c1", status="completed", answer="ok", confidence=1.0)
    with patch("app.api.routes.agent_service.run", new=AsyncMock(return_value=canned)):
        resp = await client.post(
            "/api/v1/agent/run",
            headers=viewer_headers,
            json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_exceeding_budget_returns_429(client, viewer_headers):
    settings = get_settings()
    canned = AgentRunResponse(conversation_id="c1", status="completed", answer="ok", confidence=1.0)
    with patch("app.api.routes.agent_service.run", new=AsyncMock(return_value=canned)):
        for _ in range(settings.rate_limit_requests):
            resp = await client.post(
                "/api/v1/agent/run",
                headers=viewer_headers,
                json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
            )
            assert resp.status_code == 200
        over_budget = await client.post(
            "/api/v1/agent/run",
            headers=viewer_headers,
            json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
        )
    assert over_budget.status_code == 429
    assert "retry-after" in {h.lower() for h in over_budget.headers}


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_is_unreachable(client, viewer_headers):
    canned = AgentRunResponse(conversation_id="c1", status="completed", answer="ok", confidence=1.0)
    with (
        patch("app.api.routes.agent_service.run", new=AsyncMock(return_value=canned)),
        patch(
            "app.security.rate_limit.aioredis.from_url",
            side_effect=ConnectionError("redis unreachable"),
        ),
    ):
        resp = await client.post(
            "/api/v1/agent/run",
            headers=viewer_headers,
            json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_different_api_keys_have_independent_budgets(
    client, viewer_headers, operator_headers
):
    settings = get_settings()
    operator_key = operator_headers["Authorization"].removeprefix("Bearer ")
    await _flush_rate_limit_keys(operator_key)

    canned = AgentRunResponse(conversation_id="c1", status="completed", answer="ok", confidence=1.0)
    with patch("app.api.routes.agent_service.run", new=AsyncMock(return_value=canned)):
        for _ in range(settings.rate_limit_requests):
            resp = await client.post(
                "/api/v1/agent/run",
                headers=viewer_headers,
                json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
            )
            assert resp.status_code == 200
        # viewer is now at budget; operator's own budget is untouched
        resp = await client.post(
            "/api/v1/agent/run",
            headers=operator_headers,
            json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
        )
    assert resp.status_code == 200
    await _flush_rate_limit_keys(operator_key)
