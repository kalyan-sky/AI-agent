"""get_deployment_status tool — wraps mock-enterprise's deployment endpoint."""

import httpx
from pydantic import BaseModel, Field

from app.agent.policies import RiskTier
from app.config import Settings
from app.tools.base import Tool, ToolError
from app.tools.health import _get


class GetDeploymentStatusInput(BaseModel):
    service: str = Field(..., min_length=1, max_length=100)


class GetDeploymentStatusTool(Tool[GetDeploymentStatusInput]):
    name = "get_deployment_status"
    description = (
        "Get a service's current deployment: revision, replica counts, and any failed pods."
    )
    input_schema = GetDeploymentStatusInput
    risk_tier = RiskTier.READ_ONLY
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: GetDeploymentStatusInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/services/{args.service}/deployment"
        try:
            resp = await _get(url, self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        resp.raise_for_status()
        return resp.json()
