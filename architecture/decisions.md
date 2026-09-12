# Architecture decisions

ADR-style log of the non-obvious calls made across this project — what
was decided, why, and what it costs. Ordered roughly by when each was
made; later entries sometimes revise earlier ones (noted where relevant).

## Summary

| # | Decision | Why (one line) |
|---|---|---|
| 1 | Plain `complete()` LLM interface, no vendor tool-calling | Provider-agnostic; the agent implements its own ReAct loop |
| 2 | Four-tier risk policy, unknown tool fails safe as HIGH_RISK | Never let an LLM-invented action auto-run |
| 3 | CRITICAL never executes, even approved — enforced at the executor | One fail-safe, enforced where it can't be bypassed by a caller |
| 4 | No Cloud SQL — self-hosted Postgres on a free-tier VM | Real recurring cost this project doesn't need |
| 5 | Direct VPC egress, not a Serverless VPC Access connector | A connector bills for 2 always-on instances at zero traffic |
| 6 | No Cloud NAT — VM keeps an ephemeral public IP | A NAT gateway is a real recurring cost; inbound is still firewalled |
| 7 | Local Terraform state, not a GCS backend | Avoids bootstrapping a bucket before Terraform can manage anything |
| 8 | Two secret categories: Terraform-generated vs. externally-sourced | Real LLM API keys never pass through `terraform apply`/state |
| 9 | mock-enterprise gated by a Cloud Run identity token, not `allUsers` | Real per-identity auth, not just a network boundary |
| 10 | Rate limiting fails open on a Redis outage | Protects cost/availability, not authorization — a blip shouldn't 500 everything |
| 11 | Config fails fast outside `environment=local` on any insecure default | A wrong env var should crash on boot, not surface as a mystery bug |
| 12 | No `User` model | Roles are static API-key/JWT claims, not persisted identities |
| 13 | n8n workflows authored + structurally validated, not live-executed here | This sandbox's egress policy blocks n8n's own `npm install` |
| 14 | Embedding provider abstraction (`huggingface` / `local-hash`) | HF downloads are blocked in this sandbox; never a code change to swap |
| 15 | `LLM_PROVIDER` defaults to the cheapest option (Claude Haiku 4.5) | Cost-consciousness was an explicit project constraint |

## 1. A plain text-completion LLM interface, not vendor tool-calling

**Context:** Three LLM providers (Anthropic, OpenAI-compatible, Gemini)
needed to be interchangeable. Each vendor's native tool-calling schema
differs enough — message role pairing, tool-result formatting, streaming
semantics — that supporting all three natively would be its own project.

**Decision:** `LLMProvider.complete(system, messages) -> str` is the only
interface. The agent describes its tools as text in the system prompt
(`app/agent/prompts.py`), asks the model to respond with a specific JSON
shape (thought/tool/arguments or final_answer/confidence), and parses
that response itself (`parse_agent_json`). This is what `app/agent/
graph.py`'s ReAct loop is built on.

**Consequences:** Swapping `LLM_PROVIDER` is a pure config change. The
tradeoff is losing each vendor's native tool-calling reliability
features (e.g. guaranteed valid JSON, forced tool selection) — mitigated
by `parse_agent_json`'s tolerant parsing and a bounded retry-via-replan
in the graph rather than assuming the first response is always clean.

## 2-3. Risk-tier policy and the CRITICAL fail-safe

**Context:** An LLM choosing what to execute against a production-style
system needs a policy layer that doesn't trust the model's own judgment
about what's safe.

**Decision:** Four tiers (`READ_ONLY`, `LOW_RISK` auto-execute;
`HIGH_RISK` pauses for human approval; `CRITICAL` never auto-executes
under any circumstance). An unknown tool name — one the LLM invented,
not in the allowlist — fails safe as `HIGH_RISK`, never `READ_ONLY`.
Approving a `HIGH_RISK` action actually runs it with the originally
requested arguments; approving anything tagged `CRITICAL` leaves it
`status="blocked"` regardless — enforced inside `app/agent/executor.py`
itself, not as a check the API layer could be bypassed around.

**Consequences:** `delete_resource`'s `run()` body is unreachable in
normal operation and documented as such rather than implemented — a
deliberate choice to make the fail-safe visible in the code, not just in
a policy doc. Covered by a dedicated regression test
(`test_agent_never_executes_critical_tool_even_if_requested`).

## 4-8. GCP cost architecture (Cloud SQL, VPC connector, Cloud NAT, state, secrets)

**Context:** Explicit project constraint: minimize real GCP spend for a
portfolio deployment, without pretending the result is production-grade
at real scale.

**Decisions:**
- Postgres/Redis/Qdrant/n8n run as containers on one Always-Free-tier
  e2-micro VM instead of Cloud SQL + Memorystore + a managed vector DB.
- Cloud Run reaches that VM via **direct VPC egress**
  (`vpc_access.network_interfaces`), not a Serverless VPC Access
  connector — the connector's minimum-2-instance billing floor would
  alone cost more than everything else in this design combined.
- The VM keeps its own ephemeral public IP for outbound package installs
  rather than a Cloud NAT gateway; every inbound port except IAP-tunneled
  SSH is firewalled to VPC-internal traffic only (see `network.tf`).
- Terraform state is local (git-ignored), not a GCS backend — avoids
  paying for and bootstrapping a bucket before Terraform can manage
  anything else. Documented as the first thing to change for a real team.
- Secrets split into Terraform-generated (DB password, JWT key, the
  app's API-key allowlist — Terraform is the only source of truth, so it
  owns the value) versus externally-sourced (LLM provider keys — added
  out-of-band via `gcloud secrets versions add` so a real key never has
  to pass through `terraform apply` or land in state at all).

**Consequences:** This is explicitly a cost/complexity tradeoff, not a
production reference architecture — self-hosting Postgres means owning
its backups and patching yourself, a call that would go the other way at
real production scale/SLA. See `infrastructure/terraform/README.md`'s
"Cost model" and "What this does NOT do" sections for the full reasoning
and what a production version would change first.

## 9. mock-enterprise: identity-token auth, not `allUsers`

**Context:** mock-enterprise has no application-level auth of its own
(it's a self-contained simulated system). Phase 17-19 initially gated it
with `ingress = INGRESS_TRAFFIC_INTERNAL_ONLY` (network-level) plus an
`allUsers` Cloud Run invoker grant — a real boundary, but not
identity-based.

**Decision (Phase 20-21):** agent-service's outbound HTTP client
(`app/tools/http.py`) now attaches a Cloud Run identity token to every
call, and mock-enterprise's invoker IAM binding is scoped to
agent-service's specific service account instead of `allUsers`.
`fetch_id_token` is a blocking call, offloaded via `asyncio.to_thread` so
it can't stall the event loop; an empty `GCP_ID_TOKEN_AUDIENCE` (the
default everywhere except the real deployment) skips this path entirely
— no behavior change for local dev, tests, or CI.

**A bug this surfaced:** `app/services/incident_service.py` had its own
separate httpx client for the exact same mock-enterprise calls
`app/tools/http.py` already handled — real duplication that would have
silently missed the identity-token fix if left as-is. Fixed by having it
reuse `app.tools.http.get` instead of maintaining a second copy.

## 10. Rate limiting fails open

**Context:** `app/security/rate_limit.py` protects `/api/v1/agent/run`
and `/api/v1/rag/search` — the two endpoints that spend real LLM/
embedding cost per call — with a Redis-backed fixed-window counter per
API key.

**Decision:** If Redis itself is unreachable, the request is allowed
through (logged as a warning), not rejected. Rate limiting exists to
protect availability and cost, not authorization; a Redis blip taking
down the entire API would be a worse outcome than a temporarily-
unenforced limit.

**Consequences:** A sustained Redis outage combined with a genuine abuse
attempt would go briefly unthrottled. Judged an acceptable tradeoff for
what this control is actually protecting against.

## 11. Fail-fast config validation outside `local`

**Context:** Insecure defaults (a placeholder JWT secret, an empty API
key allowlist, `DATABASE_URL` still containing `change-me`) are fine —
necessary, even — for local dev, but must never silently run in a real
environment.

**Decision:** A `model_validator` in `app/config.py` raises at
`Settings()` construction time — i.e. at process boot — when
`environment != "local"` and any of these (plus, later,
`FAILURE_INJECTION_ENABLED`) are still at their insecure default. All
problems are collected and reported together, not one-at-a-time.

**Consequences:** A misconfigured staging/prod deploy now fails loudly
on startup instead of surfacing later as a confusing auth failure or,
worse, an unintentionally open endpoint.

## 12. No `User` model

**Context:** Considered during the Phase 12-13 security/DB pass: should
agent-service persist its own user records?

**Decision:** No. Roles are static API-key/JWT-role claims (`app/
security/`), not persisted identities, and `Conversation.user_id` already
carries an external reference as a plain string. A `User` table would be
a second, redundant source of truth for identity this service doesn't
own — the kind of premature abstraction this project's own conventions
(CLAUDE.md) explicitly call out to avoid.

## 13. n8n: authored and validated, not live-executed, here

**Context:** This sandbox's egress policy blocks `cdn.sheetjs.com`, a
transitive dependency of one of n8n's own built-in nodes — n8n itself
cannot be `npm install`ed here, so the 5 workflow JSON files and the
custom node package could not be imported into a running n8n and fired
for real from within this environment.

**Decision:** Author the workflow JSON against n8n's real export schema
and the custom node's TypeScript against `n8n-workflow`'s real (verified,
not guessed) type definitions; validate what's achievable without a live
n8n — `scripts/validate_n8n_workflows.py`'s structural checks, and a real
`tsc` compile + Node smoke-test of the compiled custom node — rather than
skip the phase or fake a result. `.github/workflows/ci.yml` re-runs both
of these on every push, on a runner that (unlike this sandbox) has full
internet access.

**Remaining gap:** CI validates structure and compilation, not an actual
running n8n firing a webhook end to end — that would need `npm install
n8n` itself to succeed in CI, which hasn't been attempted. Documented in
`n8n/README.md`'s "Running these live" section as the next step for
whoever picks this up with normal network access.

## 14. Embedding provider abstraction

**Context:** `sentence-transformers` model downloads from Hugging Face
are blocked in this sandbox.

**Decision:** `EMBEDDING_PROVIDER` config switch: `huggingface` (real
embeddings, needs network on first run) or `local-hash` (deterministic,
zero-network, explicitly documented as a sandbox-only fallback — not a
retrieval-quality replacement). Swapping is a config change.

## 15. Cheapest-first LLM default

**Context:** Explicit cost-consciousness constraint, plus access to
Anthropic, Gemini, and OpenRouter API keys with a request to compare
pricing.

**Decision:** `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-haiku-4-5` by
default, with an optional configured fallback provider/model used only
if the primary fails after its own retries (`FallbackLLM` in
`app/agent/llm_provider.py`) — verified against Anthropic's own current
pricing at the time (via the `claude-api` skill) rather than assumed;
Gemini/OpenRouter pricing could not be independently verified from this
sandbox (both domains blocked) and was flagged as such rather than
guessed.

## A bug worth naming: LangGraph's `recursion_limit`

Not a design decision so much as a real bug this project caught by
actually running the graph rather than trusting the design on paper:
LangGraph's default `recursion_limit` (25) tripped *before*
`AGENT_MAX_ITERATIONS` (8) did, because one logical ReAct iteration spans
several graph node executions (`reason_and_act`, `execute_tool`,
`observe`, occasionally `replan`) plus fixed upfront overhead. Fixed in
`app/agent/graph.py::run` by deriving `recursion_limit` from
`max_iterations` (`max(50, max_iterations * 6 + 10)`) instead of trusting
the library default, with a regression test
(`test_agent_never_hits_langgraph_recursion_limit_at_default_max_iterations`)
that would fail again if this regressed.
