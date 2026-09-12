"""Agent-level eval harness — a small battery of realistic incidents run
through the *real* LangGraph agent graph, scored against expectations
about what a competent investigation should do (call a relevant tool,
reach a minimum confidence, land on a sane status).

This is deliberately different from `tests/test_agent.py`: those are
correctness tests for the graph's wiring (routing, risk-tier gating,
error handling) with a scripted fake LLM. This is a *behavioral* eval —
it runs against whichever LLM_PROVIDER is actually configured, real
model reasoning included, when a real API key is present. `make eval`
runs it (`python -m tests.eval_agent`), not `pytest`.

Costs a handful of small LLM calls (one investigation per case, each a
few short turns) when a real key is configured — cheap, but not free;
this is not run automatically in CI for that reason (see
.github/workflows/ci.yml, which only ever exercises the FakeLLM path via
tests/test_agent.py). Falls back to a scripted FakeLLM "dry run" when no
key is configured, which validates the harness's own mechanics (it can
run every case and score the result) rather than any real answer
quality — clearly labeled as such in the output.
"""

import asyncio
import sys
from dataclasses import dataclass, field
from unittest.mock import patch

from app.agent.graph import run as run_graph
from app.agent.state import AgentState
from app.config import Settings, get_settings
from tests.test_agent import FakeLLM


@dataclass
class EvalCase:
    name: str
    message: str
    expected_any_of_tools: list[str]
    min_confidence: float = 0.3
    expected_status: str = "completed"
    # A plausible scripted trace for dry-run mode only — real-LLM mode
    # ignores this entirely and lets the actual model decide.
    dry_run_script: list[str] = field(default_factory=list)


CASES: list[EvalCase] = [
    EvalCase(
        name="failed_deployment",
        message="Payment service is failing in production. Investigate and tell me what happened.",
        expected_any_of_tools=["get_service_health", "get_deployment_status", "search_knowledge"],
        dry_run_script=[
            "incident_investigation",
            '["check health", "check deployment"]',
            '{"thought": "check health", "tool": "get_service_health", '
            '"arguments": {"service": "payment-service"}}',
            '{"thought": "deployment likely bad", "final_answer": '
            '"payment-service has a failed deployment causing pod crashes", "confidence": 0.85}',
        ],
    ),
    EvalCase(
        name="database_outage",
        message="Checkout service is throwing 500s for every request. What's going on?",
        expected_any_of_tools=["get_service_health", "get_service_logs"],
        dry_run_script=[
            "incident_investigation",
            '["check logs"]',
            '{"thought": "check logs", "tool": "get_service_logs", '
            '"arguments": {"service": "checkout-service"}}',
            '{"thought": "db connection errors in logs", "final_answer": '
            '"checkout-service logs show database connection failures", "confidence": 0.8}',
        ],
    ),
    EvalCase(
        name="rollback_requires_approval",
        message="Roll back the payment-service deployment right now.",
        expected_any_of_tools=["rollback_deployment"],
        expected_status="needs_approval",
        min_confidence=0.0,
        dry_run_script=[
            "incident_investigation",
            '["rollback"]',
            '{"thought": "roll it back", "tool": "rollback_deployment", '
            '"arguments": {"service": "payment-service"}}',
        ],
    ),
]


def _settings() -> Settings:
    return get_settings()


async def _run_case(case: EvalCase, settings: Settings, dry_run: bool) -> tuple[bool, str]:
    initial_state = AgentState(
        conversation_id=f"eval-{case.name}", user_id="eval", message=case.message
    )
    if dry_run:
        with patch("app.agent.graph.build_llm", return_value=FakeLLM(case.dry_run_script)):
            final = await run_graph(initial_state, settings)
    else:
        final = await run_graph(initial_state, settings)

    problems = []
    if final.status != case.expected_status:
        problems.append(f"status={final.status!r}, expected {case.expected_status!r}")
    if final.confidence < case.min_confidence:
        problems.append(f"confidence={final.confidence} < {case.min_confidence}")
    called_tools = {a.tool for a in final.actions}
    if not called_tools & set(case.expected_any_of_tools):
        problems.append(
            f"called {called_tools or '{}'}, expected one of {case.expected_any_of_tools}"
        )

    if problems:
        return False, "; ".join(problems)
    return True, f"status={final.status}, confidence={final.confidence}, tools={called_tools}"


async def main() -> int:
    settings = _settings()
    provider_key = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "gemini": settings.google_api_key,
    }[settings.llm_provider]
    dry_run = not provider_key

    print(f"Agent eval — {len(CASES)} case(s), LLM_PROVIDER={settings.llm_provider}")
    if dry_run:
        print("No API key configured for the selected provider — DRY RUN (FakeLLM).")
        print("This validates the harness's own mechanics, not real answer quality.")
    print()

    passed = 0
    for case in CASES:
        ok, detail = await _run_case(case, settings, dry_run)
        print(f"[{'PASS' if ok else 'FAIL'}] {case.name}: {detail}")
        passed += ok

    print(f"\n{passed}/{len(CASES)} passed" + (" (dry run)" if dry_run else ""))
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
