"""Agent state — the single source of truth passed between LangGraph nodes.

A Pydantic model, not a bare dict: every node gets validation and type
hints on read. Nodes return a partial dict of fields to update (LangGraph
merges it into state); they never mutate a shared global or hidden state.
"""

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ToolCallRecord(BaseModel):
    tool: str
    arguments: dict = Field(default_factory=dict)
    risk_tier: str
    status: str  # "executed" | "pending_approval" | "blocked" | "error"
    result: dict | None = None
    error: str | None = None


class AgentState(BaseModel):
    conversation_id: str
    user_id: str
    message: str

    current_task: str = ""
    intent: str = ""
    plan: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)

    observations: list[str] = Field(default_factory=list)
    tool_results: list[dict] = Field(default_factory=list)
    retrieved_documents: list[dict] = Field(default_factory=list)
    actions: list[ToolCallRecord] = Field(default_factory=list)

    # Scratch fields set by the "reason_and_act" node for the next node to
    # consume; cleared implicitly by being overwritten each iteration.
    pending_thought: str = ""
    pending_tool: str | None = None
    pending_arguments: dict = Field(default_factory=dict)
    pending_final_answer: str | None = None
    pending_confidence: float = 0.0

    iterations: int = 0
    max_iterations: int = 8

    confidence: float = 0.0
    errors: list[str] = Field(default_factory=list)

    final_answer: str = ""
    status: str = "in_progress"  # in_progress | completed | needs_approval | error
