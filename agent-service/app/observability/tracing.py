"""Distributed tracing (OpenTelemetry) — off by default (Settings.otel_enabled),
so there's zero overhead unless explicitly turned on. When enabled, spans
cover the request boundary (FastAPI auto-instrumentation), every outbound
HTTP call (httpx auto-instrumentation — this is what actually shows
agent-service -> mock-enterprise and agent-service -> the LLM provider as
connected spans in one trace, not separate logs to correlate by hand),
and the agent's own reasoning loop (manual spans — see app/agent/graph.py
and app/agent/executor.py) so a trace shows *which* iteration made *which*
tool call, not just that some HTTP calls happened.
"""

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter

from app.config import Settings

if TYPE_CHECKING:
    from fastapi import FastAPI

_configured = False


def configure_tracing(settings: Settings, app: "FastAPI | None" = None) -> None:
    """Idempotent — safe to call more than once (tests construct the
    FastAPI app repeatedly); only the first call with otel_enabled=True
    actually sets anything up."""
    global _configured
    if not settings.otel_enabled or _configured:
        return

    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)

    exporter: SpanExporter
    if settings.otel_exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint or None)
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()
    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)

    _configured = True


def get_tracer(name: str) -> trace.Tracer:
    """A no-op tracer (from the default, un-configured global provider)
    when tracing is disabled — start_as_current_span() calls throughout
    the agent code are then free to always be present, not conditional on
    settings.otel_enabled at every call site."""
    return trace.get_tracer(name)
