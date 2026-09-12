"""DB-unavailable failure paths (per CLAUDE.md's testing checklist).

Uses a genuinely closed TCP port (127.0.0.1:1) rather than mocking the
database driver — asyncpg refuses that connection immediately (no
timeout to wait out), so this is a real, live-verified "Postgres is down"
scenario, not a simulated one.
"""

from unittest.mock import patch

import pytest

from app.agent.state import AgentState
from app.api.schemas import AgentRunRequest
from app.config import Settings
from app.memory import long_term
from app.services import agent_service
from tests.test_agent import FakeLLM

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://aiops:devpassword@127.0.0.1:1/aiops"


def _unreachable_db_settings(**overrides) -> Settings:
    return Settings(
        qdrant_local_path="/tmp/nonexistent-agent-test-qdrant",
        mock_enterprise_base_url="http://127.0.0.1:9",
        database_url=UNREACHABLE_DATABASE_URL,
        agent_max_iterations=8,
        agent_timeout_s=10,
        **overrides,
    )


@pytest.mark.asyncio
async def test_load_conversation_context_degrades_to_empty_when_db_is_unreachable():
    history = await long_term.load_conversation_context("c1", _unreachable_db_settings())
    assert history == ""


@pytest.mark.asyncio
async def test_save_agent_run_propagates_when_db_is_unreachable():
    # save_agent_run itself just surfaces the failure — app/services/
    # agent_service.py is the layer that decides how to handle it (see
    # the two agent_run tests below).
    state = AgentState(conversation_id="c1", user_id="u1", message="hi", status="completed")
    with pytest.raises(Exception):  # noqa: B017 - any DB-layer exception qualifies here
        await long_term.save_agent_run("hi", state, _unreachable_db_settings())


@pytest.mark.asyncio
async def test_agent_run_still_answers_when_db_is_completely_unreachable():
    """A Postgres outage must degrade conversation memory/audit-trail
    persistence, not take out the agent's ability to investigate at all —
    the investigation itself needs the LLM and mock-enterprise, not
    Postgres."""
    script = [
        "general",
        "[]",
        '{"thought": "hi", "final_answer": "hello there", "confidence": 0.9}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        response = await agent_service.run(
            AgentRunRequest(conversation_id="c1", user_id="u1", message="hi"),
            _unreachable_db_settings(),
        )
    assert response.status == "completed"
    assert response.answer == "hello there"
    assert response.approval_id is None


@pytest.mark.asyncio
async def test_agent_run_reports_error_when_approval_cannot_be_persisted_and_db_is_down():
    """The one case where DB unavailability must NOT be silently degraded:
    a HIGH_RISK action needs a persisted Approval row to ever be
    actionable by a human. Reporting "needs_approval" here would strand
    it — there would be nothing to approve against."""
    script = [
        "incident_investigation",
        '["rollback"]',
        '{"thought": "roll it back", "tool": "rollback_deployment", "arguments": {"service": "x"}}',
    ]
    with patch("app.agent.graph.build_llm", return_value=FakeLLM(script)):
        response = await agent_service.run(
            AgentRunRequest(conversation_id="c1", user_id="u1", message="roll back x"),
            _unreachable_db_settings(),
        )
    assert response.status == "error"
    assert "approval could not be recorded" in response.answer
    assert response.approval_id is None
