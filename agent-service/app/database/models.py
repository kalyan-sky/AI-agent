"""SQLAlchemy models: conversation memory + agent/tool execution audit trail.

Ticket/Incident data lives in mock-enterprise's own store (it's simulating
a real external system — duplicating it here would just be two sources of
truth for the same thing); these tables are what belongs to *this*
service: conversations, the messages in them, each agent run, each tool
call within a run, and human approval decisions on gated tool calls.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # Every Mapped[datetime] column is timezone-aware (TIMESTAMPTZ) so it
    # matches the timezone-aware datetime.now(UTC) values app/memory writes
    # — a naive TIMESTAMP column rejects an aware datetime at the driver
    # level (asyncpg), not silently truncating it.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(unique=True, index=True)
    user_id: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    executions: Mapped[list["AgentExecution"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    request_message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="in_progress")
    confidence: Mapped[float] = mapped_column(default=0.0)
    final_answer: Mapped[str] = mapped_column(Text, default="")
    iterations: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    conversation: Mapped["Conversation"] = relationship(back_populates="executions")
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        back_populates="agent_execution", cascade="all, delete-orphan"
    )


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_execution_id: Mapped[int] = mapped_column(ForeignKey("agent_executions.id"), index=True)
    tool_name: Mapped[str]
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_tier: Mapped[str]
    status: Mapped[str]
    result: Mapped[dict | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime]

    agent_execution: Mapped["AgentExecution"] = relationship(back_populates="tool_executions")
    approval: Mapped["Approval | None"] = relationship(
        back_populates="tool_execution", uselist=False, cascade="all, delete-orphan"
    )


class Approval(Base):
    __tablename__ = "approvals"
    # Matches repository.list_pending_approvals: filters status='pending',
    # orders by requested_at — one composite index serves both.
    __table_args__ = (Index("ix_approvals_status_requested_at", "status", "requested_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_execution_id: Mapped[int] = mapped_column(
        ForeignKey("tool_executions.id"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(default="pending")  # pending | approved | rejected
    requested_at: Mapped[datetime]
    decided_at: Mapped[datetime | None] = mapped_column(default=None)
    decided_by: Mapped[str | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)

    tool_execution: Mapped["ToolExecution"] = relationship(back_populates="approval")
