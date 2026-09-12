"""Executor unit tests: risk-tier gating, argument validation, and timeout
handling — independent of the LLM/graph layer.
"""
import asyncio

import pytest
from pydantic import BaseModel

from app.agent.executor import execute
from app.agent.policies import RiskTier
from app.tools.base import Tool, ToolError


class EchoInput(BaseModel):
    value: str


class EchoTool(Tool[EchoInput]):
    name = "echo"
    description = "Echoes the input."
    input_schema = EchoInput
    risk_tier = RiskTier.READ_ONLY
    timeout_s = 1.0

    async def run(self, args: EchoInput) -> dict:
        return {"echoed": args.value}


class SlowTool(EchoTool):
    name = "slow_echo"
    timeout_s = 0.05

    async def run(self, args: EchoInput) -> dict:
        await asyncio.sleep(1)
        return {"echoed": args.value}


class FailingTool(EchoTool):
    name = "failing_echo"

    async def run(self, args: EchoInput) -> dict:
        raise ToolError("upstream exploded")


class HighRiskTool(EchoTool):
    name = "high_risk_echo"
    risk_tier = RiskTier.HIGH_RISK


class CriticalTool(EchoTool):
    name = "critical_echo"
    risk_tier = RiskTier.CRITICAL


@pytest.mark.asyncio
async def test_execute_runs_read_only_tool():
    registry = {"echo": EchoTool()}
    record = await execute("echo", {"value": "hi"}, registry)
    assert record.status == "executed"
    assert record.result == {"echoed": "hi"}


@pytest.mark.asyncio
async def test_execute_unknown_tool_fails_safe_as_high_risk():
    record = await execute("does_not_exist", {}, {})
    assert record.status == "error"
    assert record.risk_tier == RiskTier.HIGH_RISK
    assert "unknown tool" in record.error


@pytest.mark.asyncio
async def test_execute_rejects_invalid_arguments_without_running_tool():
    registry = {"echo": EchoTool()}
    record = await execute("echo", {"wrong_field": 1}, registry)
    assert record.status == "error"
    assert "invalid arguments" in record.error


@pytest.mark.asyncio
async def test_execute_gates_high_risk_tool_without_running_it():
    registry = {"high_risk_echo": HighRiskTool()}
    record = await execute("high_risk_echo", {"value": "hi"}, registry)
    assert record.status == "pending_approval"
    assert record.result is None


@pytest.mark.asyncio
async def test_execute_blocks_critical_tool_without_running_it():
    registry = {"critical_echo": CriticalTool()}
    record = await execute("critical_echo", {"value": "hi"}, registry)
    assert record.status == "blocked"
    assert record.result is None


@pytest.mark.asyncio
async def test_execute_times_out():
    registry = {"slow_echo": SlowTool()}
    record = await execute("slow_echo", {"value": "hi"}, registry)
    assert record.status == "error"
    assert record.error == "timed out"


@pytest.mark.asyncio
async def test_execute_catches_tool_error():
    registry = {"failing_echo": FailingTool()}
    record = await execute("failing_echo", {"value": "hi"}, registry)
    assert record.status == "error"
    assert "upstream exploded" in record.error
