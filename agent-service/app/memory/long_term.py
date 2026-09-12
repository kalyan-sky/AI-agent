"""Long-term (persisted) memory: conversation history across separate
agent runs, plus the agent/tool execution audit trail.

Bounded by both message count and total characters (MAX_HISTORY_MESSAGES /
MAX_HISTORY_CHARS) so a long-running conversation's context never grows
unboundedly — old messages are dropped, not summarized, which is a
deliberate simplicity trade-off: an LLM-based summarizer would keep more
signal but costs an extra call on every turn; truncation costs nothing
and is enough to demonstrate multi-turn continuity for this project.
"""

import structlog

from app.agent.state import AgentState
from app.config import Settings
from app.database.session import get_session_factory
from app.memory import repository

logger = structlog.get_logger(__name__)

MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 4000


async def load_conversation_context(conversation_id: str, settings: Settings) -> str:
    """A compact text block of prior turns for this conversation, or ""
    if there's no history yet (first turn)."""
    session_factory = get_session_factory(settings)
    async with session_factory() as session:
        messages = await repository.get_recent_messages(
            session, conversation_id, MAX_HISTORY_MESSAGES
        )

    if not messages:
        return ""

    text = "\n".join(f"{m.role}: {m.content}" for m in messages)
    if len(text) > MAX_HISTORY_CHARS:
        text = "...(earlier context truncated)...\n" + text[-MAX_HISTORY_CHARS:]
    return text


async def save_agent_run(
    request_message: str, final_state: AgentState, settings: Settings
) -> int | None:
    """Persist the user message, the assistant's final answer (if any),
    the AgentExecution record, and one ToolExecution row per tool call —
    plus an Approval row for any call still pending human sign-off.

    Returns the new Approval's id when this run produced one, else None.
    """
    session_factory = get_session_factory(settings)
    approval_id: int | None = None

    async with session_factory() as session:
        conversation = await repository.get_or_create_conversation(
            session, final_state.conversation_id, final_state.user_id
        )
        await repository.add_message(session, conversation, "user", request_message)
        if final_state.final_answer:
            await repository.add_message(
                session, conversation, "assistant", final_state.final_answer
            )

        execution = await repository.create_agent_execution(session, conversation, request_message)
        await repository.complete_agent_execution(
            session,
            execution,
            status=final_state.status,
            confidence=final_state.confidence,
            final_answer=final_state.final_answer,
            iterations=final_state.iterations,
        )

        for action in final_state.actions:
            tool_execution = await repository.add_tool_execution(
                session,
                execution,
                tool_name=action.tool,
                arguments=action.arguments,
                risk_tier=str(action.risk_tier),
                status=action.status,
                result=action.result,
                error=action.error,
            )
            if action.status == "pending_approval":
                approval = await repository.create_approval(session, tool_execution)
                approval_id = approval.id

        await session.commit()

    logger.info(
        "agent_run_persisted",
        conversation_id=final_state.conversation_id,
        execution_status=final_state.status,
        approval_id=approval_id,
    )
    return approval_id
