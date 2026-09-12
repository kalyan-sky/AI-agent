"""Runtime failure injection (app/testing/failure_injection.py) — each of
the 5 named targets actually breaks the dependency it claims to, and
nothing breaks when injection is off (the default).
"""

import httpx
import pytest

from app.agent.llm_provider import LLMTransientError, build_llm
from app.config import Settings
from app.database.session import get_session_factory
from app.rag.qdrant import _cached_client, get_client
from app.tools import http


def _settings(target: str = "", **overrides) -> Settings:
    return Settings(
        failure_injection_enabled=bool(target),
        failure_injection_target=target,
        qdrant_local_path="/tmp/failure-injection-test-qdrant",
        database_url="postgresql+asyncpg://aiops:devpassword@127.0.0.1:5432/aiops",
        **overrides,
    )


def test_disabled_by_default_never_affects_anything():
    settings = _settings()
    assert settings.failure_injection_enabled is False
    # None of the guarded paths should raise when it's off.
    get_client(settings)
    get_session_factory(settings)
    _cached_client.cache_clear()


@pytest.mark.asyncio
async def test_llm_timeout_makes_every_completion_fail():
    settings = _settings("llm_timeout", anthropic_api_key="unused")
    llm = build_llm(settings)
    with pytest.raises(LLMTransientError, match="llm_timeout"):
        await llm.complete("system", [])


def test_qdrant_down_raises_before_touching_the_real_client():
    settings = _settings("qdrant_down")
    with pytest.raises(ConnectionError, match="qdrant_down"):
        get_client(settings)


def test_postgres_down_raises_before_building_an_engine():
    settings = _settings("postgres_down")
    with pytest.raises(ConnectionError, match="postgres_down"):
        get_session_factory(settings)


@pytest.mark.asyncio
async def test_enterprise_timeout_raises_a_real_httpx_timeout():
    settings = _settings("enterprise_timeout")
    with pytest.raises(httpx.TimeoutException):
        await http.get("http://127.0.0.1:9/whatever", 1.0, settings=settings)


@pytest.mark.asyncio
async def test_enterprise_500_returns_a_real_500_response():
    settings = _settings("enterprise_500")
    resp = await http.get("http://127.0.0.1:9/whatever", 1.0, settings=settings)
    assert resp.status_code == 500
    with pytest.raises(httpx.HTTPStatusError):
        resp.raise_for_status()


@pytest.mark.asyncio
async def test_unrecognized_target_injects_nothing():
    # Belt-and-suspenders: an unmatched target string must behave exactly
    # like "off", not like "everything" — the real (failing) network call
    # proceeds instead, against a port nothing listens on.
    settings = _settings("some_other_target")
    with pytest.raises(httpx.TransportError):
        await http.get("http://127.0.0.1:9/definitely-not-listening", 0.5, settings=settings)