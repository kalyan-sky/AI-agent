import pytest


@pytest.mark.asyncio
async def test_unseeded_service_defaults_healthy(client):
    resp = await client.get("/services/inventory-service/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["desired_replicas"] == body["available_replicas"] == 3


@pytest.mark.asyncio
async def test_payment_service_defaults_to_failed_deployment(client):
    health = (await client.get("/services/payment-service/health")).json()
    assert health["status"] == "degraded"
    assert health["available_replicas"] == 1

    deployment = (await client.get("/services/payment-service/deployment")).json()
    assert deployment["available_replicas"] == 1
    assert len(deployment["failed_pods"]) == 2

    logs = (await client.get("/services/payment-service/logs")).json()
    assert any("Back-off restarting" in entry["message"] for entry in logs)


@pytest.mark.asyncio
async def test_seeding_a_scenario_changes_all_three_endpoints(client):
    resp = await client.post(
        "/admin/scenarios/checkout-service", json={"scenario": "database_outage"}
    )
    assert resp.status_code == 200

    health = (await client.get("/services/checkout-service/health")).json()
    assert health["status"] == "unhealthy"
    assert "database" in health["detail"]

    logs = (await client.get("/services/checkout-service/logs")).json()
    assert any("OperationalError" in entry["message"] for entry in logs)


@pytest.mark.asyncio
async def test_invalid_scenario_name_is_422(client):
    resp = await client.post(
        "/admin/scenarios/checkout-service", json={"scenario": "not-a-real-scenario"}
    )
    assert resp.status_code == 422
