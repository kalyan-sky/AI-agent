# Enterprise AI Operations Agent Platform (AI-Ops Agent)

An enterprise-style AI agent that investigates production incidents — e.g.
*"Payment service is failing in production. Investigate the issue and tell
me what happened."* — by combining a multi-step LangGraph agent, RAG over
enterprise runbooks (Qdrant + Hugging Face embeddings), tool use against a
mock enterprise API (service health, deployments, tickets, incidents),
PostgreSQL-backed conversation memory, human-in-the-loop approval for risky
actions, and self-hosted n8n as the automation front door. Deployable to GCP
(Cloud Run + Cloud SQL + Compute Engine) via Terraform, with CI/CD in GitHub
Actions.

Full documentation set (architecture, API, security, deployment, interview
guide) lands as the project reaches later build phases — see `architecture/`
and the root-level `*.md` files as they're added. This README tracks
what's built and how to run it right now.

## Status

| Phase | Area | Status |
|---|---|---|
| 1 | Local dev environment (Docker Compose + native fallback) | ✅ done |
| 2 | FastAPI service (agent/RAG/tickets routes, API-key auth, RBAC) | ✅ done |
| 3 | Mock enterprise API (service catalog, tickets, incidents, seedable scenarios) | ✅ done |
| 4-5 | RAG ingestion pipeline (9 runbooks -> Qdrant), embeddings, notebooks | ✅ done |
| 6-27 | Agent graph, memory, n8n, DB models, tests, Docker, GCP, Terraform, CI/CD, docs | planned |

Branching: per-phase feature branches merged into `main`; `main` deploys to
staging once the deployment phases land, after which ongoing work moves to
a `dev` branch cut from `main`.

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
4 passed
```

## Tests

```
make test
```
