---
title: Security Guidelines for Automated Agents
category: security
service: null
environment: all
---

# Security Guidelines for Automated Agents

## Action risk tiers

Every action an automated agent can take against production is classified
into one of four tiers:

- **READ_ONLY** — reading logs, health, deployment status, tickets. Always
  safe to execute autonomously.
- **LOW_RISK** — reversible, low-blast-radius actions like a rolling
  restart or scaling within pre-approved bounds. May execute autonomously
  under policy, but every execution is logged.
- **HIGH_RISK** — actions with real customer or data impact if wrong: a
  deployment rollback, restarting a stateful service, modifying
  production configuration. Requires explicit human approval before
  execution, every time.
- **CRITICAL** — deleting resources, modifying access control, anything
  hard to reverse. Never executed autonomously under any policy; a human
  must perform the action directly, the agent may at most prepare and
  recommend it.

## Why this matters for an LLM-driven agent

An agent that reasons about an incident and proposes a fix is not the same
as an agent that executes that fix. Keeping "propose" and "execute"
separate — with a human approval gate between them for anything above
LOW_RISK — bounds the damage an incorrect model output can cause: a wrong
diagnosis becomes a wrong *suggestion*, not a wrong *rollback*.

## Tool allowlisting

Agents must only call a fixed, reviewed set of tools with validated input
schemas — never arbitrary shell commands or unvalidated free-form
parameters. Every tool call is logged with its arguments and result before
and after execution.
