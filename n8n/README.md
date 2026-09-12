# n8n orchestration layer

This directory holds the n8n side of the AI-Ops Agent platform: five
workflow definitions (`workflows/`) and one custom community node package
(`custom-nodes/n8n-nodes-aiops-agent/`) that lets those workflows call
`agent-service` without a raw HTTP Request node in every workflow.

## Why these files are authored, not live-executed, in this environment

This sandbox's egress policy blocks the hosts n8n's own `npm install`
needs (e.g. `cdn.sheetjs.com`, a transitive dependency of one of n8n's
built-in nodes), so n8n itself cannot be installed and run here. Given
that constraint, this phase was completed on a different, real basis:

- The workflow JSON was hand-authored against n8n's actual export schema
  (top-level `name`/`nodes`/`connections`/`settings`/`id`, per-node
  `parameters`/`id`/`name`/`type`/`typeVersion`/`position`) and validated
  structurally — see `scripts/validate_n8n_workflows.py` below.
- The custom node/credential TypeScript was compiled for real with `tsc`
  against the actual `n8n-workflow@^2.16.0` type definitions (not
  guessed), and the compiled output was smoke-tested in Node — see
  `custom-nodes/n8n-nodes-aiops-agent/README.md`.
- Real end-to-end execution (importing into a running n8n, firing a
  webhook, watching the agent respond) is documented below for you to run
  wherever n8n *can* reach the network — your laptop, or GitHub Actions
  in CI, both of which have normal internet access.

## Workflows

| File | Name | Trigger | Purpose |
|---|---|---|---|
| `01-incident-intake.json` | Incident Intake | `POST /webhook/incident-intake` | Authenticates the caller via a shared-secret header, validates the required fields, and hands the message to the agent. Front door for external systems (e.g. a paging tool) that don't call agent-service directly. |
| `02-ai-incident-investigation.json` | AI Incident Investigation | `POST /webhook/incident-investigation` | Pre-fetches relevant runbook context via `/api/v1/rag/search`, runs the agent, and routes to the Human Approval sub-workflow when the agent's response is `needs_approval`. |
| `03-human-approval.json` | Human Approval | Execute Workflow (sub-workflow) | Classifies whether the incoming result actually needs a human decision, waits on a resume webhook for that decision, and submits it to `/api/v1/approvals/{id}/decision`. |
| `04-error-handling.json` | Error Handling | Error Trigger | Wired as the `errorWorkflow` for the other workflows. Distinguishes retryable failures (timeouts, 5xx, 429) — backs off and retries the failed workflow — from non-retryable ones, for which it opens an incident in mock-enterprise instead of failing silently. |
| `05-notification.json` | Notification | `POST /webhook/notify` | Runs the agent, files a ticket in mock-enterprise with the answer, and hands off to a notification step (a `NoOp` placeholder — swap in a Slack/Email node for a real deployment). |

Each workflow's `settings.errorWorkflow` points at Error Handling's
workflow id, and the IF-branch hand-off from AI Incident Investigation to
Human Approval uses `executeWorkflow` by id — both cross-references are
checked by the validation script below.

## Validating the workflow files

```bash
python3 scripts/validate_n8n_workflows.py
```

This checks, without needing n8n installed: JSON validity, required
top-level keys, unique non-empty node names/ids, that every connection
references a node that actually exists, that cross-workflow id references
(`errorWorkflow`, `executeWorkflow`) resolve to a workflow file that
exists, and that no two workflows claim the same webhook path.

## Running these live (on a machine with normal internet access)

1. Install n8n and the custom node:
   ```bash
   npx n8n
   # in a separate terminal, build and link the custom node —
   # see custom-nodes/n8n-nodes-aiops-agent/README.md
   ```
2. In the n8n UI, create the `AI-Ops Agent API` credential (base URL +
   API key — see the custom node's README) and, for workflows that call
   mock-enterprise directly (Error Handling, Notification), set the
   `MOCK_ENTERPRISE_BASE_URL` environment variable n8n runs with.
3. Import each file under `workflows/` (Workflows → Import from File).
   Import `04-error-handling.json` first so the other workflows'
   `errorWorkflow` reference resolves, and `03-human-approval.json`
   before `02-ai-incident-investigation.json` for the same reason.
4. Activate each workflow, then trigger the front doors with curl, e.g.:
   ```bash
   curl -X POST http://localhost:5678/webhook/incident-intake \
     -H "Content-Type: application/json" \
     -H "X-Webhook-Secret: $N8N_INCIDENT_INTAKE_SECRET" \
     -d '{"conversation_id":"c1","user_id":"u1","message":"Payment service is failing in production"}'
   ```

## CI

Because GitHub Actions runners have normal internet access, the CI
pipeline (see `.github/workflows/`) is the place this project gets real
live validation of these workflows (installing n8n, importing the files,
firing a webhook) rather than the structural checks above — planned for
the CI/CD phase.
