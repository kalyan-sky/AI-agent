"""Load test against a running agent-service — `make load-test`, or
directly: `locust -f locustfile.py --host http://127.0.0.1:8000`.

Weighted toward the cheap, LLM-free endpoints (/health, /ready,
/api/v1/rag/search) since this project's whole cost-conscious design
means load-testing /api/v1/agent/run at any real volume would either
need a real (paid) LLM key or would mostly measure the rate limiter and
the LLM-auth-failure error path rather than real agent throughput —
still included, at low weight, since observing the rate limiter actually
engage under load is itself a meaningful signal (see README's "Verified
locally" results for a real run's numbers).
"""

from locust import HttpUser, between, task

from app.config import get_settings


def _first_api_key(role: str) -> str:
    settings = get_settings()
    for entry in settings.api_keys.split(","):
        key, _, entry_role = entry.strip().partition(":")
        if entry_role == role:
            return key
    raise RuntimeError(f"no configured API key for role={role!r} — check agent-service/.env")


class AgentServiceUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self) -> None:
        self.viewer_headers = {"Authorization": f"Bearer {_first_api_key('viewer')}"}

    @task(5)
    def health(self) -> None:
        self.client.get("/health")

    @task(3)
    def ready(self) -> None:
        self.client.get("/ready")

    @task(3)
    def rag_search(self) -> None:
        self.client.post(
            "/api/v1/rag/search",
            headers=self.viewer_headers,
            json={"query": "payment service deployment failure"},
        )

    @task(1)
    def agent_run(self) -> None:
        self.client.post(
            "/api/v1/agent/run",
            headers=self.viewer_headers,
            json={
                "conversation_id": "load-test",
                "user_id": "load-test",
                "message": "Payment service is failing in production",
            },
            timeout=30,
        )
