"""Agent graph tests using a deterministic fake LLM — no network, no API key,
no cost. This exercises the *real* graph wiring (LangGraph nodes/routing,
tool execution, risk-tier gating) end to end; only the LLM call itself is
faked, with scripted responses per call in the order the graph makes them.
"""

from unittest.mock import patch

import pytest

from app.agent.graph import run as run_graph
from app.agent.state import AgentState
from app.api.schemas import AgentRunRequest
from app.config import Settings
from app.services import agent_service


class FakeLLM:
    """Returns each scripted response in order, then repeats the last one."""

    def __init__(self, script: list[str]):
        self._script = list(script)
        self._calls: list[str] = []

    async def complete(self, system: str, messages) -> str:
        self._calls.append(system)
        if self._script:
            return self._script.pop(0)
        return '{"final_answer": "ran out of script", "confidence": 0.1}'


def _settings(**overrides) -> Settings:
    return Settings(
        qdrant_local_path="/tmp/nonexistent-agent-test-qdrant",
        mock_enterprise_base_url="http://127.0.0.1:9",  # nothing listens here
        database_url="postgresql+asyncpg://aiops:devpassword@127.0.0.1:5432/aiops",
        agent_max_iterations=8,
        agent_timeout_s=10,
        **overrides,
    )


@pytest.mark.asyncio
async def test_agent_completes_with_a_read_only_tool_call():
    script = [
        "incident_investigation",
        '["check service health", "search knowledge base"]',
        '{"thought": "check health", "tool": "get_service_health", '
        '"arguments": {"service": "payment-service"}}',
        '{"thought": "done", "final_answer": "payment-service is degraded", "confidence": 0.8}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(conversation_id="c1", user_id="u1", message="payment-service is down")
        final = await run_graph(state, _settings())

    assert final.status == "completed"
    assert final.final_answer == "payment-service is degraded"
    assert final.confidence == 0.8
    assert final.intent == "incident_investigation"
    assert len(final.actions) == 1
    assert final.actions[0].tool == "get_service_health"
    # mock-enterprise isn't reachable at the bogus URL above, so the READ_ONLY
    # tool call executes (not gated) but fails — proving the graph handles a
    # tool error gracefully instead of crashing.
    assert final.actions[0].status == "error"


@pytest.mark.asyncio
async def test_agent_treats_unregistered_tool_as_fail_safe_error():
    script = [
        "incident_investigation",
        '["do something"]',
        '{"thought": "try it", "tool": "totally_made_up_tool", "arguments": {}}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(conversation_id="c1", user_id="u1", message="do the thing")
        final = await run_graph(state, _settings())

    # A tool name the LLM invented that isn't in the registry fails safe
    # as HIGH_RISK/error rather than silently running something unvetted.
    assert final.actions[0].tool == "totally_made_up_tool"
    assert final.actions[0].status == "error"
    assert "unknown tool" in (final.actions[0].error or "")


@pytest.mark.asyncio
async def test_agent_needs_approval_for_high_risk_tool():
    """rollback_deployment is a real, registered HIGH_RISK tool — the
    graph must pause for human approval rather than execute it, and stop
    there (status="needs_approval") without ever calling the tool's run().
    """
    script = [
        "incident_investigation",
        '["rollback"]',
        '{"thought": "roll it back", "tool": "rollback_deployment", "arguments": {"service": "x"}}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(conversation_id="c1", user_id="u1", message="roll back payment-service")
        final = await run_graph(state, _settings())

    assert final.status == "needs_approval"
    assert final.actions[0].tool == "rollback_deployment"
    assert final.actions[0].status == "pending_approval"
    assert final.actions[0].result is None  # never actually executed


@pytest.mark.asyncio
async def test_agent_never_executes_critical_tool_even_if_requested():
    script = [
        "incident_investigation",
        '["delete it"]',
        '{"thought": "delete it", "tool": "delete_resource", "arguments": {"resource": "prod-db"}}',
        '{"thought": "done", "final_answer": "cannot delete autonomously", "confidence": 0.9}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(conversation_id="c1", user_id="u1", message="delete prod-db")
        final = await run_graph(state, _settings())

    assert final.actions[0].tool == "delete_resource"
    assert final.actions[0].status == "blocked"
    assert final.actions[0].result is None


@pytest.mark.asyncio
async def test_agent_respects_max_iterations():
    # Every reason_and_act call requests the same tool forever -> the loop
    # must still terminate at max_iterations rather than running forever.
    script = ["general", "[]"] + [
        '{"thought": "again", "tool": "get_service_health", "arguments": {"service": "x"}}'
    ] * 10
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(
            conversation_id="c1", user_id="u1", message="loop forever", max_iterations=3
        )
        final = await run_graph(state, _settings())

    assert final.status == "completed"
    assert final.iterations >= 3
    assert final.iterations <= 4  # bounded, not runaway


@pytest.mark.asyncio
async def test_agent_recovers_from_invalid_json_response():
    script = [
        "general",
        "[]",
        "this is not JSON at all",
        '{"thought": "ok now", "final_answer": "recovered", "confidence": 0.6}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(conversation_id="c1", user_id="u1", message="hello")
        final = await run_graph(state, _settings())

    assert final.status == "completed"
    assert final.final_answer == "recovered"
    assert any("invalid agent JSON" in e for e in final.errors)


@pytest.mark.asyncio
async def test_agent_never_hits_langgraph_recursion_limit_at_default_max_iterations():
    """Regression test: LangGraph's own recursion_limit counts every node
    execution, not our `iterations` counter — one ReAct iteration spans
    3-4 nodes, so the default max_iterations=8 needs ~30+ node executions
    and used to blow through LangGraph's default recursion_limit=25 with
    an unhandled GraphRecursionError before our own iteration cap ever
    triggered the graceful forced-finalization path (see graph.py's
    `run()`). Every iteration here returns invalid JSON, forcing the loop
    to actually run the full max_iterations budget rather than stopping
    early.
    """
    script = ["general", "[]"] + ["not valid json"] * 20
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(
            conversation_id="c1", user_id="u1", message="never resolves", max_iterations=8
        )
        final = await run_graph(state, _settings())

    assert final.status == "completed"
    assert final.iterations >= 8


@pytest.mark.asyncio
async def test_agent_service_maps_graph_result_to_response():
    script = [
        "general",
        "[]",
        '{"thought": "hi", "final_answer": "hello there", "confidence": 0.9}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        response = await agent_service.run(
            AgentRunRequest(conversation_id="c1", user_id="u1", message="hi"), _settings()
        )

    assert response.status == "completed"
    assert response.answer == "hello there"
    assert response.confidence == 0.9


@pytest.mark.asyncio
async def test_agent_service_never_500s_on_an_internal_crash():
    class ExplodingLLM:
        async def complete(self, system, messages):
            raise RuntimeError("boom")

    with patch("app.agent.graph.build_llm", return_value=ExplodingLLM()):
        response = await agent_service.run(
            AgentRunRequest(conversation_id="c1", user_id="u1", message="hi"), _settings()
        )

    assert response.status == "error"
    assert "unexpected error" in response.answer
