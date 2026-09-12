import pytest


@pytest.mark.asyncio
async def test_agent_run_echoes_conversation_id(client, viewer_headers):
    resp = await client.post(
        "/api/v1/agent/run",
        headers=viewer_headers,
        json={
            "conversation_id": "conv-001",
            "user_id": "user-123",
            "message": "Payment service is failing in production",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == "conv-001"
    assert body["status"] == "completed"
    assert 0.0 <= body["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_agent_run_rejects_empty_message(client, viewer_headers):
    resp = await client.post(
        "/api/v1/agent/run",
        headers=viewer_headers,
        json={"conversation_id": "c1", "user_id": "u1", "message": ""},
    )
    assert resp.status_code == 422
