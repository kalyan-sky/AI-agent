import pytest


@pytest.mark.asyncio
async def test_get_seed_ticket(client):
    resp = await client.get("/tickets/TICKET-1001")
    assert resp.status_code == 200
    assert resp.json()["service"] == "payment-service"


@pytest.mark.asyncio
async def test_get_missing_ticket_is_404(client):
    resp = await client.get("/tickets/NOPE")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_and_update_ticket(client):
    created = await client.post(
        "/tickets",
        json={"title": "test ticket", "description": "desc", "priority": "low"},
    )
    assert created.status_code == 201
    ticket_id = created.json()["ticket_id"]
    assert created.json()["status"] == "open"

    updated = await client.patch(f"/tickets/{ticket_id}", json={"status": "resolved"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"
    assert updated.json()["priority"] == "low"  # untouched field preserved


@pytest.mark.asyncio
async def test_update_missing_ticket_is_404(client):
    resp = await client.patch("/tickets/NOPE", json={"status": "resolved"})
    assert resp.status_code == 404
