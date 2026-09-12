"""Action risk-tier policy.

READ_ONLY  -> always auto-executed.
LOW_RISK   -> auto-executed, but every execution is logged as a policy
              decision (not just a tool call) so it's auditable.
HIGH_RISK  -> requires human approval before execution; the executor
              returns "pending_approval" and never calls the tool itself.
CRITICAL   -> never executed autonomously under any policy — the
              executor always returns "blocked".

An unknown tool name defaults to HIGH_RISK (fail safe) rather than
READ_ONLY — better to needlessly gate a real tool than to silently permit
something unregistered to run.
"""

from enum import StrEnum


class RiskTier(StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"


def requires_approval(tier: RiskTier) -> bool:
    return tier in (RiskTier.HIGH_RISK, RiskTier.CRITICAL)


def is_autonomous(tier: RiskTier) -> bool:
    return tier in (RiskTier.READ_ONLY, RiskTier.LOW_RISK)
