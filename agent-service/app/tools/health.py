"""get_service_health and get_service_logs — wrap mock-enterprise's service catalog."""

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.agent.policies import RiskTier
from app.config import Settings
from app.tools.base import Tool, ToolError


class ServiceNameInput(BaseModel):
    service: str = Field(..., min_length=1, max_length=100)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.2, max=2),
    retry=retry_if_exception_type(httpx.TransportError),
)
async def _get(url: str, timeout_s: float) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        return await client.get(url)


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
            resp = await _get(url, self.timeout_s)
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
            resp = await _get(url, self.timeout_s)
        except httpx.TransportError as exc:
            raise ToolError(f"mock-enterprise unreachable: {exc}") from exc
        resp.raise_for_status()
        return {"logs": resp.json()}
