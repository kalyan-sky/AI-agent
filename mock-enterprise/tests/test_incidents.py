import pytest


@pytest.mark.asyncio
async def test_create_and_list_incident(client):
    created = await client.post(
        "/incidents",
        json={"title": "payment-service down", "service": "payment-service", "severity": "high"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["incident_id"].startswith("INC-")
    assert body["status"] == "open"

    listed = await client.get("/incidents")
    assert listed.status_code == 200
    assert any(i["incident_id"] == body["incident_id"] for i in listed.json())
