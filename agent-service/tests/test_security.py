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


@pytest.mark.asyncio
async def test_viewer_key_cannot_decide_approvals(client, viewer_headers):
    # decide_approval requires operator or higher; a viewer key must 403
    # before the request ever reaches approval_service.
    resp = await client.post(
        "/api/v1/approvals/1/decision",
        headers=viewer_headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_responses_carry_defensive_security_headers(client):
    resp = await client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers["content-security-policy"] == "default-src 'none'"
    # local dev is plain HTTP — HSTS would be actively wrong here
    assert "strict-transport-security" not in {h.lower() for h in resp.headers}
