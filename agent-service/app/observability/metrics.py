"""Prometheus metrics — one shared registry (the library's default) scraped
via GET /metrics (see app/api/routes.py). Deliberately unauthenticated,
like /health and /ready: it's read-only aggregate counts, not sensitive
data, and requiring a bearer token here would just complicate hooking up
a standard Prometheus scrape config for no real security benefit on an
internally-network-scoped endpoint.
"""

from prometheus_client import Counter, Histogram

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests handled",
    labelnames=["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "path"],
)

agent_runs_total = Counter(
    "agent_runs_total",
    "Total agent investigation runs, by final status",
    labelnames=["status"],
)

agent_run_duration_seconds = Histogram(
    "agent_run_duration_seconds",
    "Agent investigation run duration in seconds",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 90, 120, 180),
)

tool_calls_total = Counter(
    "tool_calls_total",
    "Total tool invocations attempted by the agent, by tool and outcome",
    labelnames=["tool", "status"],
)
