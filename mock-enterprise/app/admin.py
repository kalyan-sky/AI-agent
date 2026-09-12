"""Admin/demo-only endpoints for controlling scenario state.

Not part of the "enterprise" surface a real system would expose — exists
purely so scripts/seed_data.sh and interview demos can flip a service
into a specific failure mode on demand.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.scenarios import ScenarioName, reset_scenarios, set_scenario

router = APIRouter(prefix="/admin", tags=["admin"])


class SetScenarioRequest(BaseModel):
    scenario: ScenarioName


@router.post("/scenarios/{service}")
async def set_service_scenario(service: str, body: SetScenarioRequest) -> dict:
    set_scenario(service, body.scenario)
    return {"service": service, "scenario": body.scenario}


@router.post("/reset")
async def reset() -> dict:
    reset_scenarios()
    return {"status": "reset"}
