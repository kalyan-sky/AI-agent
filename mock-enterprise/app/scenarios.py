"""Seedable failure scenarios for the service catalog.

Each scenario defines what /services/{service}/health, /deployment, and
/logs return for that service. A service's active scenario lives in
process memory and can be changed via POST /admin/scenarios/{service}
(see scripts/seed_data.sh) without restarting — that's what lets a demo
walk the same service through "healthy" -> "failed deployment" -> etc.
"""
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class ScenarioName(StrEnum):
    healthy = "healthy"
    failed_deployment = "failed_deployment"
    database_outage = "database_outage"
    api_timeout = "api_timeout"
    high_latency = "high_latency"
    auth_failure = "auth_failure"


def _now() -> datetime:
    return datetime.now(UTC)


def build_health(service: str, scenario: ScenarioName) -> dict:
    by_scenario = {
        ScenarioName.healthy: {
            "status": "healthy",
            "desired_replicas": 3,
            "available_replicas": 3,
            "detail": None,
        },
        ScenarioName.failed_deployment: {
            "status": "degraded",
            "desired_replicas": 3,
            "available_replicas": 1,
            "detail": "2 pods in CrashLoopBackOff",
        },
        ScenarioName.database_outage: {
            "status": "unhealthy",
            "desired_replicas": 3,
            "available_replicas": 3,
            "detail": "readiness probe failing: database connection refused",
        },
        ScenarioName.api_timeout: {
            "status": "degraded",
            "desired_replicas": 3,
            "available_replicas": 3,
            "detail": "downstream dependency timing out after 30s",
        },
        ScenarioName.high_latency: {
            "status": "degraded",
            "desired_replicas": 3,
            "available_replicas": 3,
            "detail": "p99 latency 4200ms (SLO: 500ms)",
        },
        ScenarioName.auth_failure: {
            "status": "degraded",
            "desired_replicas": 3,
            "available_replicas": 3,
            "detail": "401s from auth-service: token signature invalid",
        },
    }
    return {"service": service, **by_scenario[scenario]}


def build_deployment(service: str, scenario: ScenarioName) -> dict:
    base = {
        "service": service,
        "revision": "v1.42.0",
        "deployed_at": (_now() - timedelta(hours=2)).isoformat(),
        "desired_replicas": 3,
    }
    if scenario == ScenarioName.failed_deployment:
        return {
            **base,
            "revision": "v1.43.0-rc1",
            "deployed_at": (_now() - timedelta(minutes=12)).isoformat(),
            "available_replicas": 1,
            "failed_pods": [
                {"pod": f"{service}-7d9f8c6b45-x2k9p", "reason": "CrashLoopBackOff", "restarts": 6},
                {"pod": f"{service}-7d9f8c6b45-m4vqz", "reason": "CrashLoopBackOff", "restarts": 4},
            ],
        }
    return {**base, "available_replicas": base["desired_replicas"], "failed_pods": []}


def build_logs(service: str, scenario: ScenarioName) -> list[dict]:
    now = _now()

    def line(offset_s: int, level: str, message: str) -> dict:
        timestamp = (now - timedelta(seconds=offset_s)).isoformat()
        return {"timestamp": timestamp, "level": level, "message": message}

    by_scenario = {
        ScenarioName.healthy: [
            line(30, "INFO", f"{service}: request completed 200 in 42ms"),
        ],
        ScenarioName.failed_deployment: [
            line(60, "ERROR", f"{service}-7d9f8c6b45-x2k9p: Back-off restarting failed container"),
            line(45, "ERROR", "Liveness probe failed: HTTP probe failed with statuscode: 500"),
            line(30, "WARN", "Readiness gate not satisfied, removing pod from service endpoints"),
        ],
        ScenarioName.database_outage: [
            line(20, "ERROR", "psycopg2.OperationalError: could not connect to server"),
            line(15, "ERROR", "connection pool exhausted, 0 of 20 connections available"),
        ],
        ScenarioName.api_timeout: [
            line(20, "ERROR", "httpx.ReadTimeout: upstream did not respond within 30000ms"),
            line(10, "WARN", "circuit breaker OPEN for downstream 'inventory-service'"),
        ],
        ScenarioName.high_latency: [
            line(20, "WARN", "slow query detected: 3800ms SELECT ... FROM orders WHERE ..."),
            line(10, "WARN", "GC pause 1200ms"),
        ],
        ScenarioName.auth_failure: [
            line(20, "ERROR", "401 Unauthorized from auth-service: token signature invalid"),
            line(10, "ERROR", "JWKS refresh failed: connection reset"),
        ],
    }
    return by_scenario[scenario]


_DEFAULT_SCENARIOS: dict[str, ScenarioName] = {
    "payment-service": ScenarioName.failed_deployment,
}

_service_scenarios: dict[str, ScenarioName] = dict(_DEFAULT_SCENARIOS)


def get_scenario(service: str) -> ScenarioName:
    return _service_scenarios.get(service, ScenarioName.healthy)


def set_scenario(service: str, scenario: ScenarioName) -> None:
    _service_scenarios[service] = scenario


def reset_scenarios() -> None:
    _service_scenarios.clear()
    _service_scenarios.update(_DEFAULT_SCENARIOS)
