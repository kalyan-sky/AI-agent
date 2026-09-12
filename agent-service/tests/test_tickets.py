"""Ticket proxy tests. The upstream call is mocked here (unit-level); the
scripts/dev_native.sh + curl verification against the real mock-enterprise
process is what proves the live integration end-to-end.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import incident_service


def _response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("GET", "http://mock-enterprise/tickets/x"),
    )


@pytest.mark.asyncio
async def test_get_ticket_success(client, viewer_headers):
    fake_ticket = {
        "ticket_id": "TICKET-1001",
        "title": "payment-service returning 500s",
        "description": "desc",
        "status": "open",
        "priority": "high",
        "service": "payment-service",
        "created_at": "2026-09-10T14:32:00Z",
        "updated_at": "2026-09-10T14:32:00Z",
    }
    with patch.object(
        incident_service, "_get", new=AsyncMock(return_value=_response(200, fake_ticket))
    ):
        resp = await client.get("/api/v1/tickets/TICKET-1001", headers=viewer_headers)
    assert resp.status_code == 200
    assert resp.json()["ticket_id"] == "TICKET-1001"


@pytest.mark.asyncio
async def test_get_ticket_not_found(client, viewer_headers):
    with patch.object(incident_service, "_get", new=AsyncMock(return_value=_response(404))):
        resp = await client.get("/api/v1/tickets/NOPE", headers=viewer_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_ticket_upstream_unavailable(client, viewer_headers):
    with patch.object(
        incident_service,
        "_get",
        new=AsyncMock(side_effect=httpx.ConnectError("connection refused")),
    ):
        resp = await client.get("/api/v1/tickets/TICKET-1001", headers=viewer_headers)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_get_ticket_requires_auth(client):
    resp = await client.get("/api/v1/tickets/TICKET-1001")
    assert resp.status_code == 401
