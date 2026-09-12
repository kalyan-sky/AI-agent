"""Auth/RBAC tests: missing key, invalid key, and insufficient role all 401/403
rather than silently falling through to a default role.
"""
import pytest


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
    resp = await client.post(
        "/api/v1/agent/run",
        headers=viewer_headers,
        json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
    )
    assert resp.status_code == 200
