"""Agent orchestration service — runs the LangGraph investigation graph
and maps its final state onto the public API response schema.
"""

import time

import structlog

from app.agent.graph import run as run_graph
from app.agent.state import AgentState
from app.api.schemas import AgentAction, AgentRunRequest, AgentRunResponse, AgentSource
from app.config import Settings
from app.memory import long_term
from app.observability.metrics import agent_run_duration_seconds, agent_runs_total

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
    start = time.perf_counter()
    try:
        final_state = await run_graph(initial_state, settings)
    except Exception as exc:  # noqa: BLE001 - an agent-internal failure must never 500 the API
        agent_run_duration_seconds.observe(time.perf_counter() - start)
        agent_runs_total.labels(status="crashed").inc()
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
    agent_run_duration_seconds.observe(time.perf_counter() - start)
    agent_runs_total.labels(status=final_state.status).inc()

    try:
        approval_id = await long_term.save_agent_run(request.message, final_state, settings)
    except Exception as exc:  # noqa: BLE001 - see the two outcomes below
        logger.error(
            "agent_run_persistence_failed",
            conversation_id=request.conversation_id,
            status=final_state.status,
            error=str(exc),
        )
        if final_state.status == "needs_approval":
            # A HIGH_RISK action needs a persisted Approval row to ever be
            # actionable — reporting "needs_approval" here would silently
            # strand it with no way for a human to ever approve it. Honest
            # failure beats a response that looks fine but leads nowhere.
            return AgentRunResponse(
                conversation_id=request.conversation_id,
                status="error",
                answer=(
                    "The investigation finished and requires approval before its "
                    "next action, but that approval could not be recorded due to "
                    "a storage failure. Please retry."
                ),
                confidence=0.0,
            )
        # Otherwise the answer itself is unaffected by a persistence
        # failure — only the conversation history/audit trail is lost —
        # so still return it rather than failing a completed investigation.
        approval_id = None

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
