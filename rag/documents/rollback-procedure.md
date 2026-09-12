---
title: Rollback Procedure
category: runbook
service: null
environment: production
---

# Rollback Procedure

This is a **HIGH_RISK** action per the agent's action-risk policy and
requires human approval before execution (see security-guidelines.md).

## Steps

1. Identify the last known-good revision (the deployment revision running
   immediately before the one suspected of causing the incident).
2. Confirm the rollback target with whoever owns the service if possible —
   rolling back also reverts any schema-compatible data migrations that
   shipped with the bad revision, which can itself be disruptive.
3. Execute the rollback (`kubectl rollout undo deployment/<name>` or the
   equivalent in your deployment tool) and watch replica availability
   return to the desired count.
4. Re-run the smoke-test suite against the rolled-back revision.
5. Open or update the incident with the rollback action taken and the
   revision rolled back to.
6. File a follow-up ticket to root-cause the bad revision before
   attempting to re-deploy it.

## What NOT to do

Never roll back and then immediately re-attempt the same deployment
without a fix — that just reproduces the incident. Never roll back a
database migration by hand outside of the deployment tool's own rollback
path; hand-rolled schema reversals are a common source of data loss.
