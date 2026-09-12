"""Tool execution: the only place tools are ever invoked.

Validates the LLM's requested arguments against the tool's Pydantic
schema, enforces the risk-tier policy (READ_ONLY/LOW_RISK auto-execute,
HIGH_RISK/CRITICAL never run here), and runs the tool under a hard
timeout. The tool registry below is the allowlist — the LLM can only ever
reach a tool that's in it, by exact name.
"""

import asyncio

import structlog
from pydantic import ValidationError

from app.agent.policies import RiskTier, requires_approval
from app.agent.state import ToolCallRecord
from app.config import Settings
from app.tools.base import Tool
from app.tools.deployment import GetDeploymentStatusTool
from app.tools.gcp import GetGcpServiceStatusTool
from app.tools.health import GetServiceHealthTool, GetServiceLogsTool
from app.tools.knowledge import SearchKnowledgeTool
from app.tools.ticket import (
    CreateIncidentTool,
    CreateTicketTool,
    GetTicketTool,
    UpdateTicketTool,
)

logger = structlog.get_logger(__name__)


def build_tool_registry(settings: Settings) -> dict[str, Tool]:
    tools: list[Tool] = [
        SearchKnowledgeTool(settings),
        GetServiceHealthTool(settings),
        GetServiceLogsTool(settings),
        GetDeploymentStatusTool(settings),
        GetTicketTool(settings),
        CreateTicketTool(settings),
        UpdateTicketTool(settings),
        CreateIncidentTool(settings),
        GetGcpServiceStatusTool(settings),
    ]
    return {tool.name: tool for tool in tools}


async def execute(
    tool_name: str | None, raw_arguments: dict, tools_by_name: dict[str, Tool]
) -> ToolCallRecord:
    if tool_name is None:
        return ToolCallRecord(
            tool="", risk_tier=RiskTier.READ_ONLY, status="error", error="no tool specified"
        )

    tool = tools_by_name.get(tool_name)
    if tool is None:
        return ToolCallRecord(
            tool=tool_name,
            arguments=raw_arguments,
            risk_tier=RiskTier.HIGH_RISK,  # unknown tool: fail safe, never auto-run
            status="error",
            error=f"unknown tool {tool_name!r}; allowed: {sorted(tools_by_name)}",
        )

    try:
        validated_args = tool.input_schema.model_validate(raw_arguments)
    except ValidationError as exc:
        return ToolCallRecord(
            tool=tool_name,
            arguments=raw_arguments,
            risk_tier=tool.risk_tier,
            status="error",
            error=f"invalid arguments: {exc}",
        )

    if requires_approval(tool.risk_tier):
        status = "pending_approval" if tool.risk_tier == RiskTier.HIGH_RISK else "blocked"
        logger.info(
            "tool_call_gated", tool=tool_name, risk_tier=tool.risk_tier.value, status=status
        )
        return ToolCallRecord(
            tool=tool_name, arguments=raw_arguments, risk_tier=tool.risk_tier, status=status
        )

    logger.info("tool_call_start", tool=tool_name, arguments=raw_arguments)
    try:
        result = await asyncio.wait_for(tool.run(validated_args), timeout=tool.timeout_s)
    except TimeoutError:
        logger.error("tool_call_timeout", tool=tool_name, timeout_s=tool.timeout_s)
        return ToolCallRecord(
            tool=tool_name,
            arguments=raw_arguments,
            risk_tier=tool.risk_tier,
            status="error",
            error="timed out",
        )
    except Exception as exc:  # noqa: BLE001 - a tool failure must never crash the graph
        logger.error("tool_call_failed", tool=tool_name, error=str(exc))
        return ToolCallRecord(
            tool=tool_name,
            arguments=raw_arguments,
            risk_tier=tool.risk_tier,
            status="error",
            error=str(exc),
        )

    logger.info("tool_call_success", tool=tool_name)
    return ToolCallRecord(
        tool=tool_name,
        arguments=raw_arguments,
        risk_tier=tool.risk_tier,
        status="executed",
        result=result,
    )
