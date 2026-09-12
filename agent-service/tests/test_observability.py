"""Error handling + observability: an unhandled exception anywhere in a
route must come back as a generic JSON 500 (never leak the exception
message), still carry the usual response headers, and /metrics must expose
the counters this service defines — not just the prometheus_client
defaults.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app as fastapi_app


async def _post_expecting_error_response(path: str, headers: dict, json: dict):
    # A handler registered for the bare `Exception` type is installed by
    # Starlette on the *outermost* ServerErrorMiddleware (see
    # app/main.py's unhandled_exception_handler docstring) rather than the
    # inner ExceptionMiddleware — it sends the real HTTP response, then
    # re-raises so an ASGI server's own error logging still sees it. A
    # real server only ever transmits the response bytes it already sent;
    # httpx's ASGITransport, driving the app in-process, re-raises that
    # same exception into the caller unless told not to — so this helper
    # uses raise_app_exceptions=False instead of the shared `client`
    # fixture, which deliberately keeps that default off so a real bug
    # surfaces loudly in every other test.
    transport = ASGITransport(app=fastapi_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.post(path, headers=headers, json=json)


@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_500_not_a_leak(viewer_headers):
    with patch(
        "app.api.routes.rag_service.search",
        new=AsyncMock(side_effect=RuntimeError("qdrant connection string leaked: secret123")),
    ):
        resp = await _post_expecting_error_response(
            "/api/v1/rag/search", viewer_headers, {"query": "payment service timeout"}
        )
    assert resp.status_code == 500
    body = resp.json()
    assert body == {"detail": "internal server error"}
    assert "secret123" not in resp.text


@pytest.mark.asyncio
async def test_unhandled_exception_response_still_carries_standard_headers(viewer_headers):
    # The exception handler's response is sent before Starlette re-raises
    # (see helper docstring above), so it still flows back through our
    # access-log/security-headers middleware rather than bypassing them.
    with patch(
        "app.api.routes.rag_service.search",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        resp = await _post_expecting_error_response(
            "/api/v1/rag/search", viewer_headers, {"query": "payment service timeout"}
        )
    assert "x-request-id" in resp.headers
    assert resp.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_metrics_endpoint_is_unauthenticated_and_exposes_custom_metrics(client):
    await client.get("/health")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
    assert "agent_runs_total" in resp.text
    assert "tool_calls_total" in resp.text


@pytest.mark.asyncio
async def test_agent_run_records_metrics(client, viewer_headers):
    from app.api.schemas import AgentRunResponse

    canned = AgentRunResponse(conversation_id="c1", status="completed", answer="ok", confidence=1.0)
    with patch("app.api.routes.agent_service.run", new=AsyncMock(return_value=canned)):
        await client.post(
            "/api/v1/agent/run",
            headers=viewer_headers,
            json={"conversation_id": "c1", "user_id": "u1", "message": "hi"},
        )
    resp = await client.get("/metrics")
    assert 'http_requests_total{method="POST",path="/api/v1/agent/run",status_code="200"}' in (
        resp.text
    )
