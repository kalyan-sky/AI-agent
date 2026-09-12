# Enterprise AI Operations Agent Platform (AI-Ops Agent)

An enterprise-style AI agent that investigates production incidents — e.g.
*"Payment service is failing in production. Investigate the issue and tell
me what happened."* — by combining a multi-step LangGraph agent, RAG over
enterprise runbooks (Qdrant + Hugging Face embeddings), tool use against a
mock enterprise API (service health, deployments, tickets, incidents),
PostgreSQL-backed conversation memory, human-in-the-loop approval for risky
actions, and self-hosted n8n as the automation front door. Deployable to GCP
(Cloud Run + Compute Engine, deliberately **not** Cloud SQL — see
`infrastructure/terraform/README.md` for the cost reasoning) via Terraform,
with CI/CD in GitHub Actions.

See `architecture/` for the full documentation set: system diagrams
(`architecture.md`), request-flow sequence diagrams
(`sequence-diagrams.md`), a decision log explaining the non-obvious calls
made throughout (`decisions.md`), and an honest production-readiness
self-assessment (`readiness-checklist.md`). This README tracks what's
built and how to run it right now.

## Status

| Phase | Area | Status |
|---|---|---|
| 1 | Local dev environment (Docker Compose + native fallback) | ✅ done |
| 2 | FastAPI service (agent/RAG/tickets routes, API-key auth, RBAC) | ✅ done |
| 3 | Mock enterprise API (service catalog, tickets, incidents, seedable scenarios) | ✅ done |
| 4-5 | RAG ingestion pipeline (9 runbooks -> Qdrant), embeddings, notebooks | ✅ done |
| 6-7 | LangGraph agent, ReAct planning, 9 allowlisted tools | ✅ done |
| 8-9 | Postgres conversation memory, agent/tool execution audit trail, human-approval workflow | ✅ done |
| 10-11 | n8n custom node + 5 orchestration workflows | ✅ done |
| 12-13 | Security hardening (fail-fast config, rate limiting, security headers) + DB indexing | ✅ done |
| 14-16 | Error handling, Prometheus metrics, DB/Qdrant failure-path tests | ✅ done |
| 17-19 | Docker, GCP architecture, Terraform (no Cloud SQL, no VPC connector) | ✅ done |
| 20-21 | CI/CD (GitHub Actions) + GCP security (identity-token service-to-service auth) | ✅ done |
| 22-27 | Docs, diagrams, demo scenarios, failure injection, eval, readiness checklist | ✅ done |

All 27 planned build phases are now code-complete on `main` (via
per-phase feature branches). What's left is entirely outside this
sandbox's reach: a real GCP project with billing enabled. Once you've run
through `infrastructure/terraform/README.md`'s "Applying for real"
section against your own project and `main` has an actual staging
deployment behind it, the natural next step is cutting a `dev` branch
from `main` for ongoing work, per the branching plan this project
followed throughout.

## Repository layout

See `CLAUDE.md` for the full structure and conventions.

## Running it

### Option A — Docker Compose (normal network environment)

```
cp .env.example .env
make up      # docker compose up -d --build
curl localhost:8000/health
curl localhost:8000/ready
open http://localhost:5678   # n8n
```

### Option B — native processes (used in this repo's dev sandbox)

Some sandboxed CI/dev environments block Docker Hub image pulls by egress
policy. `scripts/dev_native.sh` runs the same services as local OS processes
instead: PostgreSQL and Redis via `apt-get install postgresql redis-server`,
Qdrant via its embedded local-mode Python client (`QDRANT_LOCAL_PATH` in
`agent-service/.env`), and the two FastAPI services via `uvicorn` in their
own virtualenvs. n8n is not started this way (see script comments) — run it
via Docker Compose or `npx n8n` wherever full internet egress is available.

```
./scripts/bootstrap.sh
./scripts/dev_native.sh
curl localhost:8000/health
curl localhost:8000/ready
```

### RAG

Enterprise runbooks live in `rag/documents/` (Markdown with YAML
frontmatter for title/category/service/environment). Ingest them into
Qdrant:

```
make rag-ingest   # or: cd agent-service && python -m app.rag.pipeline
```

Embeddings are provider-agnostic (`EMBEDDING_PROVIDER` in `.env`):
`huggingface` (default, `sentence-transformers`, needs normal internet on
first run to download the model) or `local-hash` (deterministic,
zero-network fallback for restricted sandboxes — not a quality
replacement, see `app/rag/embeddings.py`). See `notebooks/` for
tokenization/embedding/inference walkthroughs and a real, fully-offline
retrieval evaluation (`04_rag_evaluation.ipynb`, 100% hit@3 on the bundled
eval set).

### Demo scenarios and agent-level eval

```
make seed        # mix of failure scenarios across several mock-enterprise services
make agent-test   # run realistic incidents against a live agent-service + print results
make eval         # behavioral eval — real LLM (small cost) if configured, else a free dry run
```

`scripts/seed_data.sh` and `tests/demo_scenarios.py` need agent-service +
mock-enterprise already running (Option A or B above).
`tests/eval_agent.py` scores the agent's tool selection, confidence, and
final status against a small battery of incidents — see its own
docstring for why this isn't run in CI (it costs real LLM calls when a
key is configured).

### Failure injection

`FAILURE_INJECTION_ENABLED` / `FAILURE_INJECTION_TARGET` in
`agent-service/.env` deterministically break one dependency at a time —
`llm_timeout`, `qdrant_down`, `postgres_down`, `enterprise_timeout`, or
`enterprise_500` — to demonstrate this project's graceful-degradation
paths live rather than only in pytest. Refused outright outside
`ENVIRONMENT=local` (see `app/config.py`'s fail-fast validation) — this
can never accidentally ship active. See `app/testing/failure_injection.py`
and `tests/test_failure_injection.py`.

### Verified locally (native mode)

```
$ curl -s localhost:9000/health
{"status":"ok","service":"mock-enterprise"}

$ curl -s localhost:8000/health
{"status":"ok","service":"agent-service","version":"0.1.0","timestamp":"..."}

$ curl -s localhost:8000/ready
{"status":"ready","components":[
  {"name":"postgres","status":"ok", ...},
  {"name":"redis","status":"ok", ...},
  {"name":"qdrant","status":"ok","detail":"embedded local-mode", ...},
  {"name":"mock_enterprise","status":"ok", ...}
]}

$ cd agent-service && python -m pytest -q
73 passed

$ cd mock-enterprise && python -m pytest -q
9 passed
```

## Tests

```
make test
```

## CI/CD

`.github/workflows/ci.yml` runs on every push/PR: lint + typecheck + test
for both services (against a real Postgres/Redis service container, not
mocks), a Docker build (no push) of both images, `terraform fmt`/`validate`
for `infrastructure/terraform`, and structural validation + a real `tsc`
compile for the n8n workflows/custom node.

`.github/workflows/cd-staging.yml` deploys to Cloud Run once CI has gone
green on `main` — never from an arbitrary branch or an unverified commit.
Authenticates via Workload Identity Federation (no service-account key);
see `infrastructure/terraform/README.md` for the one-time setup (the repo
variables it needs come straight out of `terraform apply`'s outputs).
