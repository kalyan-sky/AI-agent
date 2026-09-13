"""Direct DB access for conversations/messages/agent+tool executions/approvals.

Kept as plain functions taking an `AsyncSession` (not a repository class)
— there's no state to hold beyond the session itself, and this keeps
`long_term.py` free to manage transaction boundaries (commit/rollback)
explicitly rather than hiding them behind an object.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import AgentExecution, Approval, Conversation, Message, ToolExecution


async def get_or_create_conversation(
    session: AsyncSession, conversation_id: str, user_id: str
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(Conversation.conversation_id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if conversation is None:
        conversation = Conversation(
            conversation_id=conversation_id, user_id=user_id, created_at=now, updated_at=now
        )
        session.add(conversation)
    else:
        # Otherwise updated_at only ever reflects creation time, never
        # actual recent activity — a retention policy keyed on it would
        # prune a conversation that's still in active use just because
        # it started a while ago (see scripts/prune_old_data.py).
        conversation.updated_at = now
    await session.flush()
    return conversation


async def add_message(
    session: AsyncSession, conversation: Conversation, role: str, content: str
) -> Message:
    message = Message(
        conversation_id=conversation.id, role=role, content=content, created_at=datetime.now(UTC)
    )
    session.add(message)
    await session.flush()
    return message


async def get_recent_messages(
    session: AsyncSession, conversation_id: str, limit: int
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .join(Conversation)
        .where(Conversation.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def create_agent_execution(
    session: AsyncSession, conversation: Conversation, request_message: str
) -> AgentExecution:
    execution = AgentExecution(
        conversation_id=conversation.id,
        request_message=request_message,
        started_at=datetime.now(UTC),
    )
    session.add(execution)
    await session.flush()
    return execution


async def complete_agent_execution(
    session: AsyncSession,
    execution: AgentExecution,
    *,
    status: str,
    confidence: float,
    final_answer: str,
    iterations: int,
) -> None:
    execution.status = status
    execution.confidence = confidence
    execution.final_answer = final_answer
    execution.iterations = iterations
    execution.completed_at = datetime.now(UTC)
    await session.flush()


async def add_tool_execution(
    session: AsyncSession,
    execution: AgentExecution,
    *,
    tool_name: str,
    arguments: dict,
    risk_tier: str,
    status: str,
    result: dict | None,
    error: str | None,
) -> ToolExecution:
    tool_execution = ToolExecution(
        agent_execution_id=execution.id,
        tool_name=tool_name,
        arguments=arguments,
        risk_tier=risk_tier,
        status=status,
        result=result,
        error=error,
        created_at=datetime.now(UTC),
    )
    session.add(tool_execution)
    await session.flush()
    return tool_execution


async def create_approval(session: AsyncSession, tool_execution: ToolExecution) -> Approval:
    approval = Approval(tool_execution_id=tool_execution.id, requested_at=datetime.now(UTC))
    session.add(approval)
    await session.flush()
    return approval


async def get_approval(session: AsyncSession, approval_id: int) -> Approval | None:
    result = await session.execute(
        select(Approval)
        .where(Approval.id == approval_id)
        .options(selectinload(Approval.tool_execution))
    )
    return result.scalar_one_or_none()


async def list_pending_approvals(session: AsyncSession) -> list[Approval]:
    result = await session.execute(
        select(Approval)
        .where(Approval.status == "pending")
        .options(selectinload(Approval.tool_execution))
        .order_by(Approval.requested_at)
    )
    return list(result.scalars().all())


async def decide_approval(
    session: AsyncSession, approval: Approval, *, status: str, decided_by: str, reason: str | None
) -> None:
    approval.status = status
    approval.decided_by = decided_by
    approval.decided_at = datetime.now(UTC)
    approval.reason = reason
    await session.flush()


async def list_conversations_older_than(
    session: AsyncSession, cutoff: datetime
) -> list[Conversation]:
    """For scripts/prune_old_data.py. Excludes any conversation with a
    still-pending approval regardless of age — deleting one would destroy
    the audit trail for a HIGH_RISK action a human hasn't decided on yet,
    which retention policy has no business doing silently."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.updated_at < cutoff)
        .where(
            ~Conversation.executions.any(
                AgentExecution.tool_executions.any(
                    ToolExecution.approval.has(Approval.status == "pending")
                )
            )
        )
        .order_by(Conversation.updated_at)
    )
    return list(result.scalars().all())


async def delete_conversation(session: AsyncSession, conversation: Conversation) -> None:
    """Cascades to its messages, agent executions, tool executions, and
    any decided approval — see the cascade="all, delete-orphan" settings
    on Conversation/AgentExecution/ToolExecution in app/database/models.py."""
    await session.delete(conversation)
    await session.flush()
