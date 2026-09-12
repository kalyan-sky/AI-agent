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


# --- Agent -------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1, max_length=128)
    user_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4000)


class AgentAction(BaseModel):
    tool: str
    risk_tier: str  # READ_ONLY | LOW_RISK | HIGH_RISK | CRITICAL
    status: str  # executed | pending_approval | blocked
    summary: str


class AgentSource(BaseModel):
    document_id: str
    title: str
    score: float


class AgentRunResponse(BaseModel):
    conversation_id: str
    status: str  # completed | needs_approval | error
    answer: str
    actions: list[AgentAction] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)
    confidence: float = 0.0


# --- RAG -----------------------------------------------------------------------


class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    service: str | None = None
    category: str | None = None
    environment: str | None = None


class RagChunkResult(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    text: str
    score: float
    metadata: dict = Field(default_factory=dict)


class RagSearchResponse(BaseModel):
    query: str
    results: list[RagChunkResult]


# --- Tickets -------------------------------------------------------------------


class TicketResponse(BaseModel):
    ticket_id: str
    title: str
    description: str
    status: str
    priority: str
    service: str | None = None
    created_at: datetime
    updated_at: datetime
