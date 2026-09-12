"""get_gcp_service_status tool.

Outside an actual GCP deployment there is no real GCP project to query,
so this honestly reports "not configured" rather than fabricating a
status the way a hardcoded fake response would. Once deployed
(GCP_PROJECT_ID set), the real implementation would call Cloud Run's
Admin API (`run.googleapis.com`) or Cloud Monitoring using the runtime
service account's Application Default Credentials — left as a documented
extension point rather than built against unverifiable credentials here.
"""

from pydantic import BaseModel, Field

from app.agent.policies import RiskTier
from app.config import Settings
from app.tools.base import Tool


class GetGcpServiceStatusInput(BaseModel):
    service: str = Field(..., min_length=1, max_length=100)


class GetGcpServiceStatusTool(Tool[GetGcpServiceStatusInput]):
    name = "get_gcp_service_status"
    description = (
        "Get a Cloud Run service's status from GCP (only meaningful when deployed to GCP)."
    )
    input_schema = GetGcpServiceStatusInput
    risk_tier = RiskTier.READ_ONLY
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: GetGcpServiceStatusInput) -> dict:
        if not self._settings.gcp_project_id:
            return {
                "status": "not_configured",
                "detail": (
                    "GCP_PROJECT_ID is not set — this agent isn't running against a "
                    "real GCP project, so no live Cloud Run status is available."
                ),
            }
        return {
            "status": "unknown",
            "detail": (
                "GCP_PROJECT_ID is set but the Cloud Run Admin API integration is "
                "not implemented yet."
            ),
        }
