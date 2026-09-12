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
        '["rollback"]',
        '{"thought": "roll it back", "tool": "rollback_deployment", "arguments": {"service": "x"}}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(conversation_id="c1", user_id="u1", message="roll back payment-service")
        final = await run_graph(state, _settings())

    # rollback_deployment isn't a registered tool at all (Phase 6-7 only
    # ships the 9 tools listed for this phase) -> unknown tool fails safe
    # as HIGH_RISK/error rather than silently running something unvetted.
    assert final.actions[0].tool == "rollback_deployment"
    assert final.actions[0].status == "error"
    assert "unknown tool" in (final.actions[0].error or "")


@pytest.mark.asyncio
async def test_agent_needs_approval_for_high_risk_registered_tool(monkeypatch):
    """A registered HIGH_RISK tool (simulated here since Phase 6-7 doesn't
    ship one yet — Phase 8-9 adds rollback/restart) must pause for human
    approval rather than execute, and the graph must stop there.
    """
    import app.agent.executor as executor_module
    from app.agent.policies import RiskTier
    from app.tools.gcp import GetGcpServiceStatusInput, GetGcpServiceStatusTool

    class FakeHighRiskTool(GetGcpServiceStatusTool):
        name = "rollback_deployment"
        risk_tier = RiskTier.HIGH_RISK
        input_schema = GetGcpServiceStatusInput

    original_build_registry = executor_module.build_tool_registry

    def patched_registry(settings):
        registry = original_build_registry(settings)
        registry["rollback_deployment"] = FakeHighRiskTool(settings)
        return registry

    monkeypatch.setattr(executor_module, "build_tool_registry", patched_registry)
    monkeypatch.setattr("app.agent.graph.build_tool_registry", patched_registry)

    script = [
        "incident_investigation",
        '["rollback"]',
        '{"thought": "roll it back", "tool": "rollback_deployment", "arguments": {"service": "x"}}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        state = AgentState(conversation_id="c1", user_id="u1", message="roll back payment-service")
        final = await run_graph(state, _settings())

    assert final.status == "needs_approval"
    assert final.actions[0].status == "pending_approval"


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
