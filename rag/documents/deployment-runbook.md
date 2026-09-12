---
title: Deployment Runbook
category: runbook
service: null
environment: production
---

# Deployment Runbook

## Standard rollout

1. CI builds and pushes an immutable image tag (never `:latest` in
   production manifests).
2. Deploy to staging first; run the smoke-test suite against it.
3. Roll out to production with a max-surge/max-unavailable rolling update
   so capacity never drops below the configured minimum during the
   rollout.
4. Watch error rate and latency dashboards for at least 10 minutes after
   the rollout completes before considering it "done" — many regressions
   only surface once real traffic hits the new pods.

## Signs a deployment is failing

- Desired replica count not reached (`available_replicas < desired_replicas`
  for more than a couple of minutes past the expected rollout window).
- New pods in `CrashLoopBackOff` or `ImagePullBackOff`
  (see kubernetes-troubleshooting.md).
- Error rate or p99 latency climbing right after the rollout started,
  correlated with the new revision's pods specifically (not the old ones).

## When to roll back vs. fix forward

Roll back immediately (see rollback-procedure.md) when: the failure is
customer-facing and severe (checkout broken, auth broken), or the root
cause isn't understood yet and every minute of investigation is minutes of
customer impact. Fix forward only when the issue is minor, well understood,
and a fix is faster to ship than a safe rollback would be.

## Canary and feature-flagged rollouts

For higher-risk changes, prefer a canary (small percentage of traffic) or
a feature flag that can be flipped off without a redeploy — this turns a
"roll back the deployment" incident into a "flip a flag" incident, which is
faster and safer.
