# n8n-nodes-aiops-agent

A custom n8n community node + credential type for the AI-Ops Agent
Platform. One node — **AI Agent Execute** — calls agent-service's
`POST /api/v1/agent/run`.

- **Input:** `conversationId`, `userId`, `message` (all required; a
  `NodeOperationError` is thrown before any network call if any is blank
  — a validation error, not an API error).
- **Output:** the raw `AgentRunResponse` JSON — `status`, `answer`,
  `actions`, `sources`, `confidence`, `approval_id`.
- **Errors:** a timeout or any non-2xx response from agent-service is
  wrapped as a `NodeApiError` (distinguishing a timeout message from a
  generic failure); with "Continue On Fail" enabled on the node, the
  error is emitted as `{ error: "..." }` on that item instead of
  stopping the workflow.
- **Credential:** `AI-Ops Agent API` (`aiOpsAgentApi`) holds the base URL
  + API key — no workflow ever embeds a raw key.

## Build

```bash
cd n8n/custom-nodes/n8n-nodes-aiops-agent
npm install
npm run build       # runs tsc -p tsconfig.json -> dist/
```

Verified in this repo: `npm run build` compiles with zero TypeScript
errors against `n8n-workflow@^2.16.0`'s real type definitions (not
guessed), and the compiled `dist/` output was smoke-tested by requiring
both classes directly in Node and checking their shape.

## Install into a running n8n

```bash
# from your n8n data directory (or wherever N8N_CUSTOM_EXTENSIONS points)
mkdir -p ~/.n8n/custom
cp -r /path/to/n8n-nodes-aiops-agent ~/.n8n/custom/
cd ~/.n8n/custom/n8n-nodes-aiops-agent && npm install && npm run build
# restart n8n — the node appears in the palette as "AI Agent Execute"
```

Or, for the Docker Compose setup in this repo, mount the built package
and set `N8N_CUSTOM_EXTENSIONS=/home/node/custom` on the `n8n` service,
volume-mounting `./n8n/custom-nodes/n8n-nodes-aiops-agent` to
`/home/node/custom/n8n-nodes-aiops-agent` (built, i.e. with `dist/`
already present, since the container doesn't run `npm install` itself).

## Configure the credential

In n8n: Credentials → New → "AI-Ops Agent API" → set **Base URL** (e.g.
`http://agent-service:8000` inside the compose network) and **API Key**
(one of the keys from agent-service's `API_KEYS` env var). Use "Test"
to confirm — it calls `GET {baseUrl}/health`.
