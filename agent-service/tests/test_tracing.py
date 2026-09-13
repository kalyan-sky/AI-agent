"""Distributed tracing (app/observability/tracing.py).

OpenTelemetry's global TracerProvider can only be set once per process —
not a testing inconvenience to mock around, a real constraint of how the
SDK works (confirmed live: a second `set_tracer_provider` call in this
same file's first draft silently no-opped with a warning instead of
taking effect). So this splits verification the way that constraint
actually allows:

  - configure_tracing()'s own gating logic (does it call
    set_tracer_provider or not, based on Settings.otel_enabled) is
    tested in-process, mocked — cheap, and doesn't touch global state.
  - Whether spans actually nest into one connected trace per agent run
    (app/services/agent_service.py's module docstring explains the real
    bug a manual live check caught here before this test existed) is
    verified in a genuinely separate process, so it can freely install a
    real TracerProvider without colliding with every other test in this
    suite that might run in the same pytest process.
"""

import json
import subprocess
import sys
import textwrap
from unittest.mock import patch

from app.config import Settings
from app.observability import tracing


def test_configure_tracing_does_nothing_when_disabled():
    tracing._configured = False
    with patch("app.observability.tracing.trace.set_tracer_provider") as mock_set:
        tracing.configure_tracing(Settings(otel_enabled=False))
    mock_set.assert_not_called()


def test_configure_tracing_sets_a_provider_when_enabled():
    tracing._configured = False
    with (
        patch("app.observability.tracing.trace.set_tracer_provider") as mock_set,
        patch("app.observability.tracing.HTTPXClientInstrumentor"),
    ):
        tracing.configure_tracing(Settings(otel_enabled=True, otel_exporter="console"))
    mock_set.assert_called_once()
    tracing._configured = False  # don't leak into other tests in this file/process


def test_configure_tracing_is_idempotent():
    tracing._configured = False
    with (
        patch("app.observability.tracing.trace.set_tracer_provider") as mock_set,
        patch("app.observability.tracing.HTTPXClientInstrumentor"),
    ):
        settings = Settings(otel_enabled=True, otel_exporter="console")
        tracing.configure_tracing(settings)
        tracing.configure_tracing(settings)
    mock_set.assert_called_once()
    tracing._configured = False


_SUBPROCESS_SCRIPT = textwrap.dedent(
    """
    import asyncio, json
    from unittest.mock import patch
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry import trace

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    from app.api.schemas import AgentRunRequest
    from app.config import Settings
    from app.services import agent_service
    from tests.test_agent import FakeLLM

    async def main():
        settings = Settings(
            otel_enabled=True,
            qdrant_local_path="/tmp/test-tracing-subprocess-qdrant",
            mock_enterprise_base_url="http://127.0.0.1:9",
            database_url="postgresql+asyncpg://aiops:devpassword@127.0.0.1:5432/aiops",
        )
        script = [
            "incident_investigation",
            '["check health"]',
            '{"thought": "check health", "tool": "get_service_health", '
            '"arguments": {"service": "payment-service"}}',
            '{"thought": "done", "final_answer": "degraded", "confidence": 0.8}',
        ]
        with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
            await agent_service.run(
                AgentRunRequest(conversation_id="c-trace", user_id="u1", message="investigate"),
                settings,
            )

    asyncio.run(main())

    spans = exporter.get_finished_spans()
    print(json.dumps([
        {
            "name": s.name,
            "trace_id": s.context.trace_id,
            "is_root": s.parent is None,
        }
        for s in spans
    ]))
    """
)


def test_enabled_tracing_produces_one_connected_trace_per_run():
    result = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_SCRIPT],
        cwd=".",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

    # structlog also writes JSON lines to stdout during the run; the
    # span summary is the one printed after asyncio.run() completes.
    spans = json.loads(result.stdout.strip().splitlines()[-1])
    names = {s["name"] for s in spans}
    assert "agent.run" in names
    assert "agent.execute_tool" in names

    root = next(s for s in spans if s["name"] == "agent.run")
    assert root["is_root"]
    trace_ids = {s["trace_id"] for s in spans}
    assert trace_ids == {root["trace_id"]}  # one connected trace, not one per node
