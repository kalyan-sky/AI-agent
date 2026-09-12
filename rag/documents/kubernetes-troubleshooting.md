---
title: Kubernetes Troubleshooting Guide
category: troubleshooting
service: kubernetes
environment: production
---

# Kubernetes Troubleshooting Guide

## ImagePullBackOff

`ImagePullBackOff` means the kubelet could not pull the container image for
a pod. Common causes: a typo in the image name or tag, the image was never
pushed to the registry, or the cluster's imagePullSecrets don't have access
to a private registry. Steps:

1. `kubectl describe pod <pod>` and check the Events section for the exact
   registry error (404 vs. 401 vs. DNS failure point to different causes).
2. Confirm the tag exists: `docker manifest inspect <image>:<tag>` or check
   the registry UI.
3. If the registry is private, verify the pod's service account references
   a valid `imagePullSecrets` entry and that the secret hasn't expired.
4. Roll back to the last known-good tag if the new image was never
   successfully pushed by CI.

## CrashLoopBackOff

`CrashLoopBackOff` means the container starts and then exits repeatedly.
Kubernetes backs off restart attempts exponentially. Steps:

1. `kubectl logs <pod> --previous` to see why the last instance died —
   this is the single most useful command for this failure mode.
2. Check for a failing liveness/readiness probe misconfigured with too
   short a timeout for a slow-starting app.
3. Check for missing environment variables or secrets the container
   expects at startup — a container that panics on missing config looks
   identical to one crashing for a real bug.
4. If restarts correlate with a recent deployment, roll back
   (see rollback-procedure.md) while root-causing.

## Pending pods / insufficient resources

A pod stuck in `Pending` usually means the scheduler cannot place it —
check `kubectl describe pod` for `FailedScheduling` events citing
insufficient CPU/memory, unsatisfied node affinity, or no nodes matching a
taint toleration.

## Readiness gate failures removing pods from service

When a pod's readiness probe fails, Kubernetes removes it from the
Service's endpoint list — traffic stops routing to it, but the pod keeps
running. This is *not* the same as CrashLoopBackOff: the process is alive,
it just isn't answering the readiness check (often because a downstream
dependency it needs, like a database, is unreachable).
