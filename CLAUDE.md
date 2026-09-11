# CLAUDE.md — Enterprise AI Operations Agent Platform (AI-Ops Agent)

Context file for Claude Code (and any engineer) working on this repository.

## What this project is

A production-style portfolio project: an enterprise AI agent that investigates
production incidents (e.g. "Payment service is failing in production") by
combining a LangGraph multi-step agent, RAG over enterprise runbooks (Qdrant),
tool use against a mock enterprise API (service health, deployments, tickets,
incidents), PostgreSQL-backed conversation memory, human-in-the-loop approval
for risky actions, and n8n as the orchestration/automation front door. It is
not a chatbot demo — it is meant to look and behave like something you'd find
inside a real SRE/DevOps org, and to be deployable to GCP (Cloud Run + Cloud
SQL + Compute Engine for n8n) via Terraform with CI/CD in GitHub Actions.

## Repository layout

```
agent-service/     FastAPI app: agent graph, tools, RAG, memory, DB, security
mock-enterprise/   Mock enterprise API (service health/deploy/logs/tickets/incidents)
rag/               Source runbook documents + ingestion pipeline
n8n/               Self-hosted n8n workflows (JSON) + one custom TypeScript node
notebooks/         Jupyter notebooks: tokenization, embeddings, HF inference, RAG eval
infrastructure/terraform/  GCP infra as code (Cloud Run, Cloud SQL, Artifact Registry, Secret Manager, IAM)
scripts/           bootstrap/test/seed/deploy helper scripts
.github/workflows/ CI (lint/test/build) and CD (deploy) pipelines
architecture/       architecture.md, sequence-diagrams.md, decisions.md
```

## Coding conventions

- Python 3.11+ (3.12 preferred where available), type hints everywhere, Pydantic v2 models for all I/O.
- FastAPI routers stay thin: request validation -> call a `services/*` function -> return schema. No business logic in `api/routes.py`.
- Tools (`app/tools/*`) are the ONLY way the agent touches the outside world. Every tool: Pydantic input/output schema, `name`, `description`, `timeout_s`, explicit try/except, structured log on call/result/error, bounded retry only for idempotent GET-style calls.
- Never let the LLM run arbitrary code or shell commands. Tools are allowlisted by name in `app/agent/executor.py`; there is no generic "run command" tool.
- Agent state lives in `app/agent/state.py` (a typed dict/`TypedDict` or Pydantic model) and is the single source of truth passed between LangGraph nodes. Nodes do not mutate hidden globals.
- Config is centralized in `app/config.py` via `pydantic-settings`, reading from environment variables. No hard-coded credentials, project IDs, hosts, or model names.
- LLM and embedding providers are behind interfaces (`app/agent/llm_provider.py` style abstraction / `app/rag/embeddings.py`) so swapping Anthropic <-> OpenAI-compatible <-> Gemini, or the HF embedding model, is a config change, not a code change.
- Keep modules small and single-purpose. Prefer several 80-150 line files over one 800-line file.
- Docstrings on public classes/functions where the *why* isn't obvious from the name; no restating-the-obvious comments.
- Structured JSON logs (`app/logging.py`) with `request_id`/`conversation_id`/`execution_id` — never log secrets, API keys, tokens, or full prompts containing credentials.

## Safety rules (agent/tools)

- Action risk tiers: `READ_ONLY` (auto), `LOW_RISK` (auto, policy-gated), `HIGH_RISK` (requires human approval), `CRITICAL` (never autonomous, always blocked pending explicit human execution).
- Every tool call must validate LLM-supplied arguments against its Pydantic input schema before execution — reject and re-prompt on validation failure, never execute partially-valid input.
- Agent loops are bounded: hard max iteration count and a wall-clock timeout enforced in `app/agent/graph.py`. No unbounded `while True` reasoning loops.
- Tool timeouts are mandatory on every network call (httpx `timeout=`), with bounded retries (max 2-3) only for read-only/idempotent operations.

## Local development commands

```
make install      # create venv, install agent-service + mock-enterprise deps
make up            # start local stack (native services in sandboxed/dev env; docker compose in normal env)
make down          # stop local stack
make test          # run pytest for agent-service and mock-enterprise
make lint          # ruff + mypy
make rag-ingest    # run the RAG ingestion pipeline against rag/documents
make seed          # seed mock-enterprise with demo scenarios
make agent-test    # run demo scenarios against the running agent API
```

Note: this repository is being developed inside a network-restricted sandbox
where Docker Hub image pulls are blocked by egress policy. `docker-compose.yml`
is written for normal environments (laptop, CI, GCP) with real Postgres/
Qdrant/n8n images. For local verification inside the sandbox, equivalent
native processes are used (apt-installed Postgres/Redis, Qdrant's embedded
local-mode client, n8n via npm) — see `scripts/dev_native.sh`.

## Testing

- `agent-service/tests/`: unit tests per module (tools, rag, memory, security) + API tests via `httpx.AsyncClient` against the FastAPI app + agent graph tests with mocked tool calls/mocked LLM.
- Always test failure paths, not just happy paths: tool timeout, invalid tool args, Qdrant unavailable, DB unavailable, max-iterations hit, invalid API key, wrong role.

## Deployment rules

- Never hard-code a GCP project ID — always `var.project_id` in Terraform / `${GCP_PROJECT_ID}` in scripts.
- Secrets come from environment variables locally and GCP Secret Manager in the cloud — never committed, never baked into images.
- Prefer Workload Identity Federation over long-lived service account keys in CI/CD.
- Cloud SQL has no public IP; Cloud Run reaches it via the Cloud SQL connector / private VPC connector.
- CI runs on every push; CD to `prod` requires the `staging` pipeline green and is not triggered from arbitrary branches.

## Development workflow

Build phase by phase (see the phase list in project history / README). After
each phase: create files, run it, run tests, fix failures, then move on. Do
not leave placeholder code that hasn't been executed at least once.
