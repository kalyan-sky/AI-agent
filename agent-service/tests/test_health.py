"""Phase 1 tests: liveness always green, readiness reflects real dependency state.

/health must never depend on external systems. /ready is tested twice: once
against whatever is actually reachable (informational — this repo's sandbox
runs Postgres/Redis/mock-enterprise natively and Qdrant in embedded mode),
and once with every dependency check patched to fail, to prove a single
down dependency correctly flips the aggregate status to "not_ready" instead
of silently reporting healthy.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.schemas import ComponentStatus


@pytest.mark.asyncio
async def test_health_is_always_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "agent-service"


@pytest.mark.asyncio
async def test_health_sets_request_id_header(client):
    resp = await client.get("/health")
    assert "x-request-id" in resp.headers


@pytest.mark.asyncio
async def test_ready_reports_component_breakdown(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    names = {c["name"] for c in body["components"]}
    assert names == {"postgres", "redis", "qdrant", "mock_enterprise"}
    assert body["status"] in {"ready", "not_ready"}


@pytest.mark.asyncio
async def test_ready_is_not_ready_when_a_dependency_is_down(client):
    down = ComponentStatus(name="postgres", status="down", detail="connection refused")
    with (
        patch("app.api.routes.check_postgres", new=AsyncMock(return_value=down)),
        patch(
            "app.api.routes.check_redis",
            new=AsyncMock(return_value=ComponentStatus(name="redis", status="ok")),
        ),
        patch(
            "app.api.routes.check_qdrant",
            new=AsyncMock(return_value=ComponentStatus(name="qdrant", status="ok")),
        ),
        patch(
            "app.api.routes.check_mock_enterprise",
            new=AsyncMock(return_value=ComponentStatus(name="mock_enterprise", status="ok")),
        ),
    ):
        resp = await client.get("/ready")
    body = resp.json()
    assert body["status"] == "not_ready"
    postgres = next(c for c in body["components"] if c["name"] == "postgres")
    assert postgres["status"] == "down"
