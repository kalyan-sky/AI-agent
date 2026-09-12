---
title: GCP Production Runbook
category: runbook
service: null
environment: production
---

# GCP Production Runbook

## Cloud Run

Cloud Run services scale on request concurrency. A service returning 429s
or timing out under load usually means `max-instances` is capped too low
for the traffic, or cold starts are too slow for the request timeout —
check the concurrency and min-instances settings before assuming it's an
application bug.

## Compute Engine (self-hosted services)

For cost-conscious deployments, stateful services (Postgres, Redis,
Qdrant, n8n) can run as containers on a single `e2-micro` instance instead
of managed offerings (Cloud SQL, Memorystore) — this fits GCP's Always
Free tier for one non-preemptible `e2-micro` per month in specific
regions, at the cost of losing managed backups/HA/patching. Document this
trade-off explicitly rather than treating a self-hosted database as
equivalent to a managed one.

## Secret Manager

Never bake secrets into container images or commit them to source control.
Cloud Run services read secrets from Secret Manager at startup via IAM,
not from environment variables set in `gcloud run deploy` — the latter is
visible in deployment history and Cloud Console.

## IAM least privilege

Each service's runtime service account should have only the roles it
needs (e.g. `roles/secretmanager.secretAccessor` for the specific secrets
it uses, not project-wide `roles/editor`). Prefer Workload Identity
Federation over long-lived service account keys for CI/CD.

## Networking

Databases and internal services should have no public IP. Cloud Run
reaches a VPC-internal database via a Serverless VPC Access connector or
the Cloud SQL Auth Proxy/connector — never by exposing the database on a
public IP with a firewall allowlist.
