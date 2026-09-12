# Sequence diagrams

## 1. Incident investigation (happy path, no approval needed)

```mermaid
sequenceDiagram
    actor Caller
    participant API as agent-service API
    participant Mem as Memory (Postgres)
    participant Graph as LangGraph agent
    participant LLM
    participant RAG as Qdrant
    participant Tools as Tool executor
    participant ME as mock-enterprise

    Caller->>API: POST /api/v1/agent/run\n{conversation_id, user_id, message}
    API->>API: auth (API key/JWT) + RBAC + rate limit
    API->>Mem: load_conversation_context(conversation_id)
    Mem-->>API: prior turns (bounded, or "" if none/unavailable)
    API->>Graph: run(AgentState)
    loop ReAct iterations (bounded by max_iterations + timeout)
        Graph->>LLM: complete(system, [task + observations])
        LLM-->>Graph: next thought + tool call (as JSON)
        alt tool call chosen
            Graph->>Tools: execute(tool_name, args)
            Tools->>Tools: validate args, check risk tier
            Tools->>ME: GET /services/{service}/health (READ_ONLY, auto)
            ME-->>Tools: health/logs/deployment data
            Tools-->>Graph: ToolCallRecord(status="executed", result)
        else final answer ready
            Graph->>Graph: node_final_response
        end
    end
    Graph-->>API: final AgentState (status=completed)
    API->>Mem: save_agent_run(...)
    Mem-->>API: approval_id=None (nothing pending)
    API-->>Caller: AgentRunResponse{status, answer, actions, sources, confidence}
```

RAG search (`search_knowledge`) follows the same tool-executor path as
any other `READ_ONLY` tool — omitted above for space; see
`app/tools/knowledge.py`.

## 2. Human-in-the-loop approval (HIGH_RISK action)

```mermaid
sequenceDiagram
    actor Caller
    participant API as agent-service API
    participant Graph as LangGraph agent
    participant Tools as Tool executor
    participant DB as Postgres
    actor Operator

    Caller->>API: POST /api/v1/agent/run\n"roll back payment-service"
    API->>Graph: run(AgentState)
    Graph->>Tools: execute("rollback_deployment", {service})
    Tools->>Tools: risk_tier == HIGH_RISK -> gate, never call run()
    Tools-->>Graph: ToolCallRecord(status="pending_approval")
    Graph->>Graph: node_needs_approval -> status="needs_approval"
    Graph-->>API: final AgentState
    API->>DB: save_agent_run(...) creates an Approval row
    DB-->>API: approval_id
    API-->>Caller: AgentRunResponse{status="needs_approval", approval_id}

    Operator->>API: GET /api/v1/approvals (role >= operator)
    API-->>Operator: pending approvals (tool, args, risk_tier)
    Operator->>API: POST /api/v1/approvals/{id}/decision {decision: "approve"}
    API->>DB: load Approval + its ToolExecution
    alt tool's risk_tier == HIGH_RISK
        API->>Tools: execute(tool_name, args, bypass_approval=True)
        Tools->>Tools: real call now runs, for real
        Tools-->>API: ToolCallRecord(status="executed"/"error")
    else CRITICAL (or anything else) even if "approve"
        API->>API: stays status="blocked" — never runs, by design
    end
    API->>DB: decide_approval(status="approved", decided_by, reason)
    API-->>Operator: ApprovalResponse{status, tool_execution_status}
```

The fail-safe this whole flow exists for: a `CRITICAL` tool's `run()` is
never called, from any code path, even an explicit "approve" decision —
enforced in `app/agent/executor.py::execute`, not just at the API layer.

## 3. Error handling — a downstream dependency fails mid-run

```mermaid
sequenceDiagram
    actor Caller
    participant API as agent-service API
    participant Graph as LangGraph agent
    participant Tools as Tool executor
    participant ME as mock-enterprise
    participant DB as Postgres

    Caller->>API: POST /api/v1/agent/run
    API->>Graph: run(AgentState)
    Graph->>Tools: execute("get_service_health", {service})
    Tools->>ME: GET /services/{service}/health
    ME--xTools: connection refused / timeout
    Tools-->>Graph: ToolCallRecord(status="error", error="...")
    Note over Graph: the graph does not crash — a failed tool call\nis just another observation for the next reasoning step
    Graph->>Graph: reason_and_act again, or reach max_iterations
    Graph-->>API: final AgentState (status="completed" or "error")
    API->>DB: save_agent_run(...)
    alt Postgres itself is unreachable
        DB--xAPI: connection refused
        Note over API: degrades — returns the computed answer anyway\n(approval_id=None) UNLESS status="needs_approval",\nwhere losing the Approval row would strand it —\nthat case returns status="error" instead
    end
    API-->>Caller: AgentRunResponse (never a bare 500\nfor an internal/dependency failure)

    Note over API: An exception that reaches the API layer\nunhandled still never leaks: caught in\ncorrelation_and_access_log middleware,\nlogged, returned as a generic 500 JSON body
```

See `tests/test_memory.py`, `tests/test_rag.py`, and
`tests/test_observability.py` for these paths exercised for real (a
genuinely closed TCP port for the DB/Qdrant cases, not mocks).
