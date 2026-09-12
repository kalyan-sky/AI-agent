"""Runs a handful of realistic incidents against a *live* agent-service +
mock-enterprise (both must already be running — see README's "Running
it" section) and prints each result. This is a manual demo/walkthrough
tool, not a pytest suite — `make agent-test` runs it directly with
`python -m tests.demo_scenarios`, not `pytest`.

Seeds mock-enterprise with one scenario per service, then asks the agent
to investigate each one — the same "Payment service is failing in
production" style prompt this whole project is built around, plus a few
others covering different failure modes.

Needs a real ANTHROPIC_API_KEY (or whichever LLM_PROVIDER is configured)
in agent-service/.env for a real answer — without one, every scenario
still runs end to end (seeding, auth, request/response) but the agent's
own answer will be a clean "could not complete the investigation" error,
which is itself the graceful-failure path this project builds toward,
just not the point of running this particular script.
"""

import asyncio
import json
import sys

import httpx

from app.config import get_settings

AGENT_BASE_URL = "http://127.0.0.1:8000"
MOCK_ENTERPRISE_BASE_URL = "http://127.0.0.1:9000"

SCENARIOS: list[tuple[str, str, str]] = [
    # (service, mock-enterprise scenario, incident message to send the agent)
    (
        "payment-service",
        "failed_deployment",
        "Payment service is failing in production. Investigate and tell me what happened.",
    ),
    (
        "checkout-service",
        "database_outage",
        "Checkout service is throwing 500s for every request. What's going on?",
    ),
    (
        "inventory-service",
        "api_timeout",
        "Customers are reporting the inventory page is timing out. Can you look into it?",
    ),
]


def _first_api_key() -> str:
    settings = get_settings()
    for entry in settings.api_keys.split(","):
        key, _, role = entry.strip().partition(":")
        if role == "viewer":
            return key
    raise SystemExit("No viewer API key configured — set API_KEYS in agent-service/.env")


async def _seed(client: httpx.AsyncClient, service: str, scenario: str) -> None:
    resp = await client.post(
        f"{MOCK_ENTERPRISE_BASE_URL}/admin/scenarios/{service}", json={"scenario": scenario}
    )
    resp.raise_for_status()


async def _run_agent(
    client: httpx.AsyncClient, api_key: str, conversation_id: str, message: str
) -> dict:
    resp = await client.post(
        f"{AGENT_BASE_URL}/api/v1/agent/run",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"conversation_id": conversation_id, "user_id": "demo-user", "message": message},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


async def main() -> int:
    api_key = _first_api_key()
    exit_code = 0

    async with httpx.AsyncClient() as client:
        try:
            await client.get(f"{AGENT_BASE_URL}/health", timeout=5)
            await client.get(f"{MOCK_ENTERPRISE_BASE_URL}/health", timeout=5)
        except httpx.TransportError as exc:
            print(f"agent-service and/or mock-enterprise aren't reachable: {exc}", file=sys.stderr)
            print("Start them first — see README's \"Running it\" section.", file=sys.stderr)
            return 1

        for i, (service, scenario, message) in enumerate(SCENARIOS, start=1):
            print(f"\n{'=' * 70}\n[{i}/{len(SCENARIOS)}] {service} -> {scenario}\n{'=' * 70}")
            await _seed(client, service, scenario)
            try:
                result = await _run_agent(client, api_key, f"demo-{service}", message)
            except httpx.HTTPStatusError as exc:
                print(f"FAILED: {exc}", file=sys.stderr)
                exit_code = 1
                continue

            print(f"status:     {result['status']}")
            print(f"confidence: {result['confidence']}")
            print(f"answer:     {result['answer']}")
            if result.get("actions"):
                print("actions:")
                for action in result["actions"]:
                    print(f"  - {action['tool']} ({action['risk_tier']}): {action['status']}")
            if result.get("sources"):
                print(f"sources:    {len(result['sources'])} runbook chunk(s) retrieved")
            print()
            print(json.dumps(result, indent=2))

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
