"""Service catalog: health, deployment status, and recent logs.

Backed by each service's active scenario (see scenarios.py) so a demo
can walk a service through different failure modes without restarting
the process.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.scenarios import build_deployment, build_health, build_logs, get_scenario

router = APIRouter()


class ServiceHealth(BaseModel):
    service: str
    status: str
    desired_replicas: int
    available_replicas: int
    detail: str | None = None


class FailedPod(BaseModel):
    pod: str
    reason: str
    restarts: int


class DeploymentStatus(BaseModel):
    service: str
    revision: str
    deployed_at: str
    desired_replicas: int
    available_replicas: int
    failed_pods: list[FailedPod]


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str


@router.get("/services/{service}/health", response_model=ServiceHealth)
async def service_health(service: str) -> ServiceHealth:
    return ServiceHealth(**build_health(service, get_scenario(service)))


@router.get("/services/{service}/deployment", response_model=DeploymentStatus)
async def service_deployment(service: str) -> DeploymentStatus:
    return DeploymentStatus(**build_deployment(service, get_scenario(service)))


@router.get("/services/{service}/logs", response_model=list[LogEntry])
async def service_logs(service: str) -> list[LogEntry]:
    return [LogEntry(**entry) for entry in build_logs(service, get_scenario(service))]
