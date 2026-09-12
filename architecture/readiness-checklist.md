# Production readiness checklist

An honest self-assessment, not a marketing claim: what's real, what's
demo-scoped, and what a real production deployment at real scale would
need to add. Written as the final phase of this project specifically so
it can be checked against the actual code rather than aspirational.

Legend: ✅ done · 🟡 partial / demo-scoped · ⬜ not done

## Security

| Item | Status | Notes |
|---|---|---|
| Authentication | ✅ | API-key allowlist (`app/security/api_key.py`) + a real JWT client-credentials validation path (`oauth.py`), never trusting an unverified token |
| Authorization / RBAC | ✅ | 3-tier role hierarchy, `require_role` dependency, tested for both 401 (bad/missing key) and 403 (insufficient role) |
| Secrets management | ✅ | No secret committed anywhere; env vars locally, GCP Secret Manager in the cloud; fail-fast config validation refuses insecure defaults outside `environment=local` |
| Rate limiting | ✅ | Redis-backed, per API key, on the two cost-bearing endpoints; fails open on a Redis outage (a deliberate choice, not an oversight — see `decisions.md`) |
| Security headers | ✅ | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, a `default-src 'none'` CSP, HSTS outside local |
| Service-to-service auth (GCP) | ✅ | Cloud Run identity token, audience-scoped, IAM invoker restricted to agent-service's own service account — not `allUsers` |
| Least-privilege IAM | ✅ | 4 separate service accounts (one per Cloud Run service, one for the VM, one for CI), each granted only the secrets/registry/invoker access it needs |
| No long-lived cloud credentials in CI | ✅ | Workload Identity Federation, scoped to one GitHub repo; no service-account key ever minted |
| Dependency/image scanning | ⬜ | Not wired into CI — no Trivy/Grype/Dependabot equivalent yet |
| Secret scanning in CI | ⬜ | Not wired into CI (no gitleaks/trufflehog step) |
| Input validation | ✅ | Every tool call validated against its Pydantic schema before execution, rejected (not partially run) on failure |
| CRITICAL action fail-safe | ✅ | Enforced at the executor, not just the API — covered by a dedicated regression test |

## Testing

| Item | Status | Notes |
|---|---|---|
| Unit tests | ✅ | Per-module coverage across tools, executor, memory, security, RAG |
| API tests | ✅ | `httpx.AsyncClient` against the real FastAPI app |
| Agent graph tests | ✅ | Real LangGraph wiring, deterministic FakeLLM (no cost) |
| Failure-path tests | ✅ | Tool timeout, invalid args, unknown tool, max-iterations, invalid API key, wrong role, DB unreachable, Qdrant unreachable — the last two against a genuinely closed TCP port, not mocks |
| Runtime failure injection | ✅ | 5 named targets, toggleable via config, refused outside `environment=local`, each with its own live test |
| Behavioral/quality eval | 🟡 | `tests/eval_agent.py` — real when an LLM key is configured (small real cost, not run in CI for that reason), a mechanics-only dry run otherwise |
| RAG retrieval eval | ✅ | `notebooks/04_rag_evaluation.ipynb` — 100% hit@3 on the bundled eval set (small, hand-built — not a claim that generalizes to a much larger corpus) |
| Load/performance testing | ⬜ | Not done — no k6/locust run against a deployed instance |
| Chaos/resilience testing beyond failure injection | 🟡 | Failure injection covers single-dependency-down scenarios; no multi-failure or sustained-load chaos testing |

## Observability

| Item | Status | Notes |
|---|---|---|
| Structured logging | ✅ | JSON logs, correlation IDs (`request_id`/`conversation_id`), secrets scrubbed defensively before emission |
| Metrics | ✅ | Prometheus `/metrics` — HTTP, agent-run, and tool-call counters/histograms, verified live against a running instance |
| Health/readiness probes | ✅ | `/health` (liveness only) vs `/ready` (checks every real downstream dependency) |
| Unhandled-exception handling | ✅ | Never leaks an internal message; still gets one access-log line and its usual response headers (a real Starlette middleware-layering bug was found and fixed here — see `decisions.md`) |
| Distributed tracing | ⬜ | No OpenTelemetry/trace propagation across agent-service -> mock-enterprise -> LLM provider |
| Alerting | 🟡 | A budget alert exists (`infrastructure/terraform/billing.tf`, opt-in); no error-rate/latency alerting on the running services themselves |
| Dashboards | ⬜ | Metrics are exposed but no Grafana/Cloud Monitoring dashboard is built |

## Reliability & resilience

| Item | Status | Notes |
|---|---|---|
| Bounded agent loops | ✅ | Hard iteration cap + wall-clock timeout + an explicit LangGraph `recursion_limit` derived from the former (a real bug here was caught and fixed — see `decisions.md`) |
| Graceful degradation | ✅ | DB-down, Qdrant-down, and mock-enterprise-down all degrade to a sane response rather than a 500, with one deliberate exception (a HIGH_RISK approval that can't be persisted reports an honest error instead of a silently-unreachable "needs_approval") |
| Retries | ✅ | Bounded, exponential backoff, only for idempotent calls (GET, not PATCH) |
| LLM fallback | ✅ | Optional secondary provider, engaged only after the primary's own retries are exhausted |
| Timeouts on every network call | ✅ | httpx `timeout=` everywhere; no unbounded wait |
| Database migrations | ✅ | Real Alembic migrations, generated via `--autogenerate` and applied against a live Postgres, not hand-written |
| Backup/disaster recovery | ⬜ | Self-hosted Postgres on the VM has no automated backup — a real production deployment would need this (see `decisions.md`'s Cloud SQL tradeoff) |
| Multi-region / high availability | ⬜ | Single VM, single region — an explicit cost tradeoff, not an oversight, for this project's scale |

## Scalability

| Item | Status | Notes |
|---|---|---|
| Stateless app tier | ✅ | agent-service/mock-enterprise hold no in-process state that would break horizontal scaling (mock-enterprise's scenario state is intentionally process-local — it's a demo/test fixture, not production data) |
| Autoscaling | ✅ | Cloud Run scale-to-zero / up to a configured max instance count |
| Connection pooling | ✅ | SQLAlchemy async engine, pooled, cached per URL |
| Database is a single point of scale-limit | 🟡 | One Postgres instance on one VM — fine at this project's traffic, would need Cloud SQL (or equivalent) + read replicas at real scale |

## Cost

| Item | Status | Notes |
|---|---|---|
| No Cloud SQL / managed Redis / managed vector DB | ✅ | Self-hosted on a free-tier VM instead — see `decisions.md` |
| No Serverless VPC Access connector | ✅ | Direct VPC egress instead — avoids its 2-instance billing floor |
| No Cloud NAT | ✅ | VM keeps a firewalled public IP instead |
| Budget alerting | 🟡 | Opt-in, not enabled by default (needs a real billing account ID) |
| LLM cost awareness | ✅ | Cheapest-first default model, rate-limited endpoints, eval harness explicitly avoids real LLM cost in CI |

## Deployment & CI/CD

| Item | Status | Notes |
|---|---|---|
| CI on every push | ✅ | Lint, typecheck, test (both services), Docker build, Terraform validate, n8n structural validation + real `tsc` compile |
| CD gated on CI success | ✅ | `workflow_run` keyed to CI's conclusion, only on `main` — never an arbitrary branch or unverified commit |
| Infrastructure as code | ✅ | Full Terraform config, validated for real against actual provider schemas in this sandbox (registry access was blocked; worked around via HashiCorp's own release distribution point) |
| IaC actually applied | ⬜ | Never run `terraform apply` — no real GCP project/credentials in this sandbox; the config is ready, not yet exercised against real infrastructure |
| Rollback strategy | 🟡 | Cloud Run's own revision history supports `gcloud run services update-traffic` rollback; not scripted/documented as a runbook step here |
| Post-deploy smoke test | ✅ | `cd-staging.yml` curls `/health` on the freshly deployed revision |

## Data & compliance

| Item | Status | Notes |
|---|---|---|
| PII handling | N/A | No real user PII flows through this system — it's a portfolio project against a simulated enterprise API |
| Audit trail | ✅ | Every agent run, tool call, and approval decision persisted with who/when/what |
| Data retention policy | ⬜ | No automated pruning of old conversations/executions — would be needed before real production use |
| Compliance framework (SOC2, etc.) | N/A | Out of scope for a portfolio project |

## Documentation

| Item | Status | Notes |
|---|---|---|
| Architecture overview + diagrams | ✅ | `architecture.md`, `sequence-diagrams.md` |
| Decision log | ✅ | `decisions.md` |
| Deployment docs | ✅ | `infrastructure/terraform/README.md`, `n8n/README.md` |
| Runbooks (the RAG content itself) | ✅ | `rag/documents/` — real markdown runbooks the agent retrieves from |
| API documentation | 🟡 | FastAPI's auto-generated OpenAPI docs (`/docs`) exist by default; no separate hand-written API reference |
| This checklist | ✅ | You're reading it |

## Bottom line

This is a genuinely production-*styled* system — real risk-tier policy
enforcement, real fail-fast config validation, real failure-path testing
against actual broken dependencies, real least-privilege IAM, a real CI
pipeline — built to demonstrate the judgment calls a production system
requires, not to fake having made them. The gaps above (backups, HA,
dependency scanning, load testing, real IaC apply) are exactly the set
of things a genuine production rollout would need on top of this, and
are named here rather than glossed over.
