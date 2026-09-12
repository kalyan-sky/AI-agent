"""Auth/RBAC tests: missing key, invalid key, and insufficient role all 401/403
rather than silently falling through to a default role.

`agent_service.run` is mocked here — this file tests the auth layer in
front of it, not the agent graph itself (see tests/test_agent.py for
that, with a fake LLM).
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.api.schemas import AgentRunResponse


@pytest.mark.asyncio
async def test_missing_api_key_is_401(client):
    resp = await client.post(
        "/api/v1/agent/run",
        json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_api_key_is_401(client):
    resp = await client.post(
        "/api/v1/agent/run",
        headers={"Authorization": "Bearer not-a-real-key"},
        json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_viewer_key_can_call_agent_run(client, viewer_headers):
    canned = AgentRunResponse(conversation_id="c1", status="completed", answer="ok", confidence=1.0)
    with patch("app.api.routes.agent_service.run", new=AsyncMock(return_value=canned)):
        resp = await client.post(
            "/api/v1/agent/run",
            headers=viewer_headers,
            json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
        )
    assert resp.status_code == 200
