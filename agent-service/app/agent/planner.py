"""LLM-driven planning steps: intent classification, the initial
investigation plan, and the per-iteration ReAct decision (next tool call
or final answer). Each function takes the current state and an LLM and
returns a partial state update — no hidden state, no side effects beyond
the LLM call itself.
"""

import json

import structlog

from app.agent.llm_provider import LLMMessage, LLMProvider
from app.agent.prompts import build_system_prompt, parse_agent_json
from app.agent.state import AgentState, Message
from app.tools.base import Tool

logger = structlog.get_logger(__name__)

INTENT_LABELS = ["incident_investigation", "knowledge_query", "ticket_management", "general"]


async def classify_intent(state: AgentState, llm: LLMProvider) -> dict:
    system = (
        "Classify the user's request into exactly one label from this list: "
        f"{', '.join(INTENT_LABELS)}. Respond with only the label, nothing else."
    )
    text = await llm.complete(system, [LLMMessage(role="user", content=state.current_task)])
    label = text.strip().lower().strip(".")
    if label not in INTENT_LABELS:
        label = "general"
    return {"intent": label}


async def make_plan(state: AgentState, llm: LLMProvider) -> dict:
    system = (
        "You are planning an SRE investigation. Given the task and its intent, "
        "list 2-5 short investigation steps as a JSON array of strings and nothing else. "
        'Example: ["Check service health", "Check recent deployment", "Search knowledge base"]'
    )
    user_content = f"Task: {state.current_task}\nIntent: {state.intent}"
    text = await llm.complete(system, [LLMMessage(role="user", content=user_content)])
    steps: list[str] = []
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            steps = [str(s) for s in parsed][:5]
        except (ValueError, TypeError) as exc:
            logger.warning("plan_parse_failed", error=str(exc), raw=text[:200])
    return {"plan": steps}


async def decide_next_action(state: AgentState, llm: LLMProvider, tools: list[Tool]) -> dict:
    system = build_system_prompt(tools)
    llm_messages = [LLMMessage(role=m.role, content=m.content) for m in state.messages]

    text = await llm.complete(system, llm_messages)

    try:
        parsed = parse_agent_json(text)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("agent_json_parse_failed", error=str(exc), raw=text[:300])
        return {
            "pending_tool": None,
            "pending_arguments": {},
            "pending_final_answer": None,
            "messages": [
                *state.messages,
                Message(role="assistant", content=text),
                Message(
                    role="user",
                    content=(
                        "Your last response was not valid JSON in the required format. "
                        "Respond with exactly one JSON object as instructed."
                    ),
                ),
            ],
            "errors": [*state.errors, f"invalid agent JSON: {exc}"],
        }

    if "final_answer" in parsed:
        return {
            "pending_thought": parsed.get("thought", ""),
            "pending_tool": None,
            "pending_arguments": {},
            "pending_final_answer": parsed["final_answer"],
            "pending_confidence": _safe_float(parsed.get("confidence"), default=0.5),
            "messages": [*state.messages, Message(role="assistant", content=text)],
        }

    return {
        "pending_thought": parsed.get("thought", ""),
        "pending_tool": parsed.get("tool"),
        "pending_arguments": parsed.get("arguments") or {},
        "pending_final_answer": None,
        "messages": [*state.messages, Message(role="assistant", content=text)],
    }


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
