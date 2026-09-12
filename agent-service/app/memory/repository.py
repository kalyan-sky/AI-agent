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
    if conversation is None:
        now = datetime.now(UTC)
        conversation = Conversation(
            conversation_id=conversation_id, user_id=user_id, created_at=now, updated_at=now
        )
        session.add(conversation)
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
