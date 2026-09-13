"""LangGraph definition for the incident-investigation agent.

Node flow:
    intake -> classify_intent -> plan -> reason_and_act
        -> [final_answer given?] -> final_response -> END
        -> [tool call given?] -> execute_tool -> observe
            -> [HIGH_RISK pending_approval?] -> needs_approval -> END
            -> [max iterations?] -> final_response -> END
            -> [every 3rd iteration] -> replan -> reason_and_act
            -> otherwise -> reason_and_act (loop)

Bounded by both a max-iteration count (AGENT_MAX_ITERATIONS) and a
wall-clock timeout (AGENT_TIMEOUT_S) — never an unbounded loop. Reasoning
artifacts (plan, thought, selected tool + arguments, tool result,
conclusion) are stored as structured state, not hidden chain-of-thought.
"""

import asyncio
import json

import structlog
from langgraph.graph import END, StateGraph

from app.agent.executor import build_tool_registry
from app.agent.executor import execute as execute_tool_call
from app.agent.llm_provider import LLMMessage, build_llm
from app.agent.planner import classify_intent, decide_next_action, make_plan
from app.agent.policies import RiskTier
from app.agent.prompts import parse_agent_json
from app.agent.state import AgentState, Message
from app.config import Settings
from app.observability.tracing import get_tracer

logger = structlog.get_logger(__name__)
tracer = get_tracer(__name__)


def build_graph(settings: Settings):
    llm = build_llm(settings)
    tools_by_name = build_tool_registry(settings)
    tools = list(tools_by_name.values())

    async def node_intake(state: AgentState) -> dict:
        return {
            "current_task": state.message,
            "messages": [Message(role="user", content=state.message)],
        }

    async def node_classify_intent(state: AgentState) -> dict:
        with tracer.start_as_current_span("agent.classify_intent"):
            return await classify_intent(state, llm)

    async def node_plan(state: AgentState) -> dict:
        with tracer.start_as_current_span("agent.plan"):
            return await make_plan(state, llm)

    async def node_reason_and_act(state: AgentState) -> dict:
        with tracer.start_as_current_span("agent.reason_and_act") as span:
            span.set_attribute("agent.iteration", state.iterations)
            return await decide_next_action(state, llm, tools)

    async def node_execute_tool(state: AgentState) -> dict:
        with tracer.start_as_current_span("agent.execute_tool") as span:
            span.set_attribute("agent.tool", state.pending_tool or "")
            record = await execute_tool_call(
                state.pending_tool, state.pending_arguments, tools_by_name
            )
            span.set_attribute("agent.tool_status", record.status)
            return {"actions": [*state.actions, record]}

    async def node_observe(state: AgentState) -> dict:
        record = state.actions[-1]
        if record.status == "executed":
            observation = f"Tool '{record.tool}' result: {_truncate(record.result)}"
        elif record.status == "pending_approval":
            observation = f"Tool '{record.tool}' requires human approval and was NOT executed."
        elif record.status == "blocked":
            observation = (
                f"Tool '{record.tool}' is CRITICAL risk and can never run autonomously. "
                "Do not attempt it again — recommend it to a human in your final answer instead."
            )
        else:
            observation = f"Tool '{record.tool}' failed: {record.error}"

        return {
            "observations": [*state.observations, observation],
            "tool_results": [*state.tool_results, record.result]
            if record.result
            else state.tool_results,
            "messages": [*state.messages, Message(role="user", content=observation)],
            "iterations": state.iterations + 1,
        }

    async def node_replan(state: AgentState) -> dict:
        return await make_plan(state, llm)

    async def node_final_response(state: AgentState) -> dict:
        if state.pending_final_answer:
            return {
                "final_answer": state.pending_final_answer,
                "confidence": state.pending_confidence,
                "status": "completed",
            }
        # Forced finalization: max iterations reached without the model concluding.
        summary = "\n".join(state.observations) or "No tool results were gathered."
        system = (
            "You ran out of investigation budget. Summarize what you found so far from "
            "the observations below and give your best-effort answer. Respond with "
            'exactly one JSON object: {"final_answer": "...", "confidence": 0.0-1.0}.'
        )
        text = await llm.complete(
            system,
            [
                LLMMessage(
                    role="user", content=f"Task: {state.current_task}\n\nObservations:\n{summary}"
                )
            ],
        )
        try:
            parsed = parse_agent_json(text)
            answer = str(parsed.get("final_answer", text))
            confidence = float(parsed.get("confidence", 0.3))
        except (ValueError, TypeError, KeyError):
            answer, confidence = text, 0.3
        return {"final_answer": answer, "confidence": confidence, "status": "completed"}

    async def node_needs_approval(state: AgentState) -> dict:
        last_action = state.actions[-1]
        return {
            "final_answer": (
                f"Investigation paused: the action '{last_action.tool}' "
                f"(risk tier {last_action.risk_tier}) requires human approval before it "
                "can run. No changes have been made."
            ),
            "status": "needs_approval",
        }

    def route_after_reason(state: AgentState) -> str:
        return "final_response" if state.pending_final_answer is not None else "execute_tool"

    def route_after_observe(state: AgentState) -> str:
        last_action = state.actions[-1]
        if last_action.risk_tier == RiskTier.HIGH_RISK and last_action.status == "pending_approval":
            return "needs_approval"
        if state.iterations >= state.max_iterations:
            return "final_response"
        if state.iterations > 0 and state.iterations % 3 == 0:
            return "replan"
        return "reason_and_act"

    graph = StateGraph(AgentState)
    graph.add_node("intake", node_intake)
    graph.add_node("classify_intent", node_classify_intent)
    graph.add_node("create_plan", node_plan)
    graph.add_node("reason_and_act", node_reason_and_act)
    graph.add_node("execute_tool", node_execute_tool)
    graph.add_node("observe", node_observe)
    graph.add_node("replan", node_replan)
    graph.add_node("final_response", node_final_response)
    graph.add_node("needs_approval", node_needs_approval)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "classify_intent")
    graph.add_edge("classify_intent", "create_plan")
    graph.add_edge("create_plan", "reason_and_act")
    graph.add_conditional_edges(
        "reason_and_act",
        route_after_reason,
        {"execute_tool": "execute_tool", "final_response": "final_response"},
    )
    graph.add_edge("execute_tool", "observe")
    graph.add_conditional_edges(
        "observe",
        route_after_observe,
        {
            "reason_and_act": "reason_and_act",
            "replan": "replan",
            "final_response": "final_response",
            "needs_approval": "needs_approval",
        },
    )
    graph.add_edge("replan", "reason_and_act")
    graph.add_edge("final_response", END)
    graph.add_edge("needs_approval", END)

    return graph.compile()


def _truncate(result: dict | None, limit: int = 2000) -> str:
    text = json.dumps(result)
    return text if len(text) <= limit else text[:limit] + "...(truncated)"


async def run(initial_state: AgentState, settings: Settings) -> AgentState:
    compiled = build_graph(settings)
    # LangGraph's own recursion_limit counts every node execution across the
    # whole run, not our domain-level `iterations` counter — one logical
    # ReAct iteration spans 3-4 nodes (reason_and_act, execute_tool, observe,
    # occasionally replan), plus fixed upfront overhead (intake,
    # classify_intent, create_plan) and a final node. Left at LangGraph's
    # default of 25 this trips *before* our own max_iterations bound does,
    # surfacing as an unhandled GraphRecursionError instead of a graceful
    # forced final answer — size it generously off max_iterations instead.
    recursion_limit = max(50, initial_state.max_iterations * 6 + 10)
    try:
        result = await asyncio.wait_for(
            compiled.ainvoke(initial_state, config={"recursion_limit": recursion_limit}),
            timeout=settings.agent_timeout_s,
        )
    except TimeoutError:
        logger.error("agent_wall_clock_timeout", conversation_id=initial_state.conversation_id)
        return initial_state.model_copy(
            update={
                "status": "error",
                "final_answer": "Investigation timed out before reaching a conclusion.",
                "errors": [*initial_state.errors, "wall-clock timeout"],
            }
        )
    return AgentState(**result)
