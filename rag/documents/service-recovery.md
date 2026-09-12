---
title: Service Recovery Runbook
category: runbook
service: null
environment: production
---

# Service Recovery Runbook

## Restarting a degraded service

A rolling restart (deleting pods one at a time so Kubernetes recreates
them) is a **LOW_RISK** action — it doesn't change what's deployed, only
forces fresh process instances. Useful when a service is stuck in a bad
in-memory state (a stale cache, a leaked connection pool, a deadlocked
worker) rather than actually crashing.

Restarting is *not* a fix for: `CrashLoopBackOff` (the new pods will crash
too), a bad deployment (roll back instead), or a downstream dependency
outage (restarting your service doesn't fix the dependency).

## Scaling up during a capacity incident

If the issue is load-driven (high latency, timeouts under traffic, but the
application code itself is healthy), scaling out (`LOW_RISK`, auto or
policy-gated) can buy time while the root cause is addressed. Scaling is
not a substitute for fixing a genuine bug or a database bottleneck — more
replicas hitting an already-saturated database just spreads the same
failure across more connections.

## Circuit breakers

When a downstream dependency is timing out, an open circuit breaker
protects the calling service from cascading failure by failing fast
instead of piling up threads/connections waiting on a dead dependency.
Seeing "circuit breaker OPEN for downstream 'X'" in logs means the real
incident is in service X, not the service reporting the open breaker.
