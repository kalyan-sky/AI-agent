"""Agent orchestration service.

The real multi-step LangGraph agent (planning, tool execution, RAG,
memory, human-in-the-loop approval) is built in a later phase. This stub
exercises the full request path — schema validation, auth, structured
logging — end to end right now, and gets replaced node-for-node without
any change to the route or its contract. It deliberately does not
fabricate an investigation or a root cause; it says plainly that
reasoning isn't wired up yet.
"""
import structlog

from app.api.schemas import AgentRunRequest, AgentRunResponse

logger = structlog.get_logger(__name__)


async def run(request: AgentRunRequest) -> AgentRunResponse:
    logger.info(
        "agent_run_stub",
        conversation_id=request.conversation_id,
        user_id=request.user_id,
    )
    return AgentRunResponse(
        conversation_id=request.conversation_id,
        status="completed",
        answer=(
            "The multi-step investigation graph (planning, tool execution, RAG, "
            "memory) is not implemented yet — this response only confirms your "
            "request was validated and authenticated correctly end-to-end."
        ),
        actions=[],
        sources=[],
        confidence=0.0,
    )
