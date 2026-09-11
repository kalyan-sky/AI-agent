"""Pydantic request/response schemas for the public API.

Kept separate from route handlers so schemas can be imported by tests,
n8n integration docs, and the OpenAPI spec without pulling in FastAPI
routing concerns.
"""
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class ComponentStatus(BaseModel):
    name: str
    status: str  # "ok" | "degraded" | "down"
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str = "0.1.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReadinessResponse(BaseModel):
    status: str  # "ready" | "not_ready"
    components: list[ComponentStatus]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
