"""get_service_health and get_service_logs — wrap mock-enterprise's service catalog."""

import httpx
from pydantic import BaseModel, Field

from app.agent.policies import RiskTier
from app.config import Settings
from app.tools import http
from app.tools.base import Tool, ToolError


class ServiceNameInput(BaseModel):
    service: str = Field(..., min_length=1, max_length=100)


class GetServiceHealthTool(Tool[ServiceNameInput]):
    name = "get_service_health"
    description = "Get a service's current health status, replica counts, and detail message."
    input_schema = ServiceNameInput
    risk_tier = RiskTier.READ_ONLY
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: ServiceNameInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/services/{args.service}/health"
        try:
            resp = await http.get(url, self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        resp.raise_for_status()
        return resp.json()


class GetServiceLogsTool(Tool[ServiceNameInput]):
    name = "get_service_logs"
    description = "Get a service's recent log lines (timestamp, level, message)."
    input_schema = ServiceNameInput
    risk_tier = RiskTier.READ_ONLY
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: ServiceNameInput) -> dict:
        url = f"{self._settings.mock_enterprise_base_url}/services/{args.service}/logs"
        try:
            resp = await http.get(url, self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        resp.raise_for_status()
        return {"logs": resp.json()}
