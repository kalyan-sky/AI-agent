"""Production-impacting remediation tools — the ones this project's
human-in-the-loop approval workflow exists for.

rollback_deployment is HIGH_RISK: it changes what's actually running, so
it always requires human approval (see app/agent/policies.py,
app/agent/executor.py). Once approved, it "rolls back" by resetting the
service's mock-enterprise scenario to healthy — a realistic stand-in for
what a real rollback accomplishes (the service becomes healthy again)
without needing a real deployment platform to roll back for real.

delete_resource is CRITICAL: it can never execute autonomously under any
policy, approved or not (see policies.py's fail-safe design) — its run()
body is documented as unreachable rather than actually implemented,
since the executor guarantees a CRITICAL tool's run() is never called.
"""

import httpx
from pydantic import BaseModel, Field

from app.agent.policies import RiskTier
from app.config import Settings
from app.tools import http
from app.tools.base import Tool, ToolError


class RollbackDeploymentInput(BaseModel):
    service: str = Field(..., min_length=1, max_length=100)


class RollbackDeploymentTool(Tool[RollbackDeploymentInput]):
    name = "rollback_deployment"
    description = (
        "Roll back a service's deployment to the last known-good state. Requires approval."
    )
    input_schema = RollbackDeploymentInput
    risk_tier = RiskTier.HIGH_RISK
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: RollbackDeploymentInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/admin/scenarios/{args.service}"
        try:
            resp = await http.post(
                url,
                {"scenario": "healthy"},
                self.timeout_s,
                audience=self._settings.gcp_id_token_audience,
                settings=self._settings,
            )
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        resp.raise_for_status()
        return {"service": args.service, "action": "rollback", "result": resp.json()}


class DeleteResourceInput(BaseModel):
    resource: str = Field(..., min_length=1, max_length=200)


class DeleteResourceTool(Tool[DeleteResourceInput]):
    name = "delete_resource"
    description = "Permanently delete a resource. NEVER executed autonomously, even with approval."
    input_schema = DeleteResourceInput
    risk_tier = RiskTier.CRITICAL
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: DeleteResourceInput) -> dict:
        # Unreachable in normal operation: the executor never calls run()
        # for a CRITICAL tool. Raising rather than silently no-opping in
        # case something ever calls this directly, bypassing the executor.
        raise ToolError(
            "delete_resource is CRITICAL risk and must be performed by a human directly"
        )
