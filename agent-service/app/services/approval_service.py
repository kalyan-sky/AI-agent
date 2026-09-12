"""Approval decision service.

Approving a HIGH_RISK tool call actually executes it now, using the
arguments the agent originally requested — the executor's approval gate
is bypassed only for that one call, only because a human just signed off.
CRITICAL actions are never executed here regardless of decision: the
executor's bypass only applies to HIGH_RISK (see app/agent/executor.py),
by design — this is the fail-safe the whole policy exists for.
"""

import structlog

from app.agent.executor import build_tool_registry, execute
from app.agent.policies import RiskTier
from app.config import Settings
from app.database.models import Approval
from app.database.session import get_session_factory
from app.memory import repository

logger = structlog.get_logger(__name__)


class ApprovalNotFoundError(Exception):
    pass


class ApprovalAlreadyDecidedError(Exception):
    def __init__(self, current_status: str):
        self.current_status = current_status
        super().__init__(f"approval already decided (status={current_status})")


async def list_pending(settings: Settings) -> list[Approval]:
    session_factory = get_session_factory(settings)
    async with session_factory() as session:
        return await repository.list_pending_approvals(session)


async def decide(
    approval_id: int, decision: str, decided_by: str, reason: str | None, settings: Settings
) -> Approval:
    session_factory = get_session_factory(settings)
    async with session_factory() as session:
        approval = await repository.get_approval(session, approval_id)
        if approval is None:
            raise ApprovalNotFoundError(approval_id)
        if approval.status != "pending":
            raise ApprovalAlreadyDecidedError(approval.status)

        tool_execution = approval.tool_execution

        if decision == "approve" and tool_execution.risk_tier == RiskTier.HIGH_RISK.value:
            tools_by_name = build_tool_registry(settings)
            record = await execute(
                tool_execution.tool_name,
                tool_execution.arguments,
                tools_by_name,
                bypass_approval=True,
            )
            tool_execution.status = record.status
            tool_execution.result = record.result
            tool_execution.error = record.error
            logger.info(
                "approved_tool_executed",
                approval_id=approval_id,
                tool=tool_execution.tool_name,
                result_status=record.status,
            )
        elif decision == "approve":
            # A CRITICAL (or otherwise non-HIGH_RISK) action stays blocked
            # even on "approve" — see module docstring.
            tool_execution.status = "blocked"
            tool_execution.error = "this risk tier is never auto-executed, even with approval"

        await repository.decide_approval(
            session,
            approval,
            status="approved" if decision == "approve" else "rejected",
            decided_by=decided_by,
            reason=reason,
        )
        await session.commit()
        # expire_on_commit=False (see session.py) — approval and its already-
        # loaded tool_execution stay populated with our in-memory updates,
        # no refresh needed.
        return approval
