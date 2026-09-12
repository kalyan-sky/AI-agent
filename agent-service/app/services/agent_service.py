"""Agent orchestration service — runs the LangGraph investigation graph
and maps its final state onto the public API response schema.
"""

import structlog

from app.agent.graph import run as run_graph
from app.agent.state import AgentState
from app.api.schemas import AgentAction, AgentRunRequest, AgentRunResponse, AgentSource
from app.config import Settings
from app.memory import long_term

logger = structlog.get_logger(__name__)


async def run(request: AgentRunRequest, settings: Settings) -> AgentRunResponse:
    history = await long_term.load_conversation_context(request.conversation_id, settings)
    task_message = request.message
    if history:
        task_message = f"Conversation so far:\n{history}\n\nNew request: {request.message}"

    initial_state = AgentState(
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        message=task_message,
        max_iterations=settings.agent_max_iterations,
    )
    try:
        final_state = await run_graph(initial_state, settings)
    except Exception as exc:  # noqa: BLE001 - an agent-internal failure must never 500 the API
        logger.error("agent_run_crashed", conversation_id=request.conversation_id, error=str(exc))
        return AgentRunResponse(
            conversation_id=request.conversation_id,
            status="error",
            answer=(
                "The agent encountered an unexpected error and could not complete "
                f"the investigation: {exc}"
            ),
            confidence=0.0,
        )

    approval_id = await long_term.save_agent_run(request.message, final_state, settings)

    logger.info(
        "agent_run_complete",
        conversation_id=request.conversation_id,
        status=final_state.status,
        iterations=final_state.iterations,
        tool_calls=len(final_state.actions),
        approval_id=approval_id,
    )

    actions = [
        AgentAction(
            tool=a.tool,
            risk_tier=str(a.risk_tier),
            status=a.status,
            summary=a.error or "ok",
        )
        for a in final_state.actions
    ]
    sources = [
        AgentSource(
            document_id=doc.get("document_id", "unknown"),
            title=doc.get("title", ""),
            score=doc.get("score", 0.0),
        )
        for result in final_state.tool_results
        if isinstance(result, dict)
        for doc in result.get("results", [])
    ]

    return AgentRunResponse(
        conversation_id=request.conversation_id,
        status=final_state.status,
        answer=final_state.final_answer or "No answer produced.",
        actions=actions,
        sources=sources,
        confidence=final_state.confidence,
        approval_id=approval_id,
    )
