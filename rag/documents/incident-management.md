---
title: Incident Management Process
category: process
service: null
environment: all
---

# Incident Management Process

## Severity levels

- **SEV1** — full outage or severe customer-facing impact (checkout down,
  data loss risk). Page immediately, all-hands until mitigated.
- **SEV2** — partial degradation affecting a subset of users or a single
  service, workaround may exist.
- **SEV3** — minor issue, no significant customer impact, handled during
  business hours.

## Lifecycle

1. **Detect** — alert fires, or a user/support ticket flags the issue.
2. **Triage** — confirm it's real (not a monitoring false positive),
   assign severity, open an incident record.
3. **Investigate** — check service health, recent deployments, logs, and
   relevant runbooks; form a hypothesis before taking action.
4. **Mitigate** — take the smallest action that stops customer impact
   (often a rollback or restart) even before the root cause is fully
   understood; full root-cause analysis can continue after impact stops.
5. **Resolve** — confirm metrics have returned to baseline.
6. **Post-incident review** — blameless review of what happened, what
   worked, and what to fix so it doesn't recur; always file a ticket for
   concrete follow-up items.

## Creating a ticket vs. an incident

An **incident** tracks the live event (what's broken, current status,
who's engaged). A **ticket** tracks a unit of work (a bug, a follow-up
task, a root-cause fix) and can outlive the incident that spawned it — a
single incident often produces several follow-up tickets.
