#!/usr/bin/env bash
# Manual deploy to the staging Cloud Run services — the same steps
# .github/workflows/cd-staging.yml runs automatically once CI is green on
# main. Useful for a first deploy (before any CI run exists to trigger
# off of) or an ad-hoc redeploy without pushing to main.
#
# Requires: gcloud CLI authenticated against the target project (either
# your own credentials or the WIF-based CI identity), and
# infrastructure/terraform already applied at least once (see
# infrastructure/terraform/README.md) so the Artifact Registry repo and
# both Cloud Run services already exist.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID to your GCP project}"
: "${GCP_REGION:=us-central1}"

TAG="$(git -C "$ROOT_DIR" rev-parse --short HEAD)"
REPO="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/ai-ops-agent"

echo "==> Configuring Docker for Artifact Registry ($REPO)"
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

for svc in agent-service mock-enterprise; do
  echo "==> Building $svc:$TAG"
  docker build -t "$REPO/$svc:$TAG" -t "$REPO/$svc:staging" "$ROOT_DIR/$svc"

  echo "==> Pushing $svc:$TAG"
  docker push "$REPO/$svc:$TAG"
  docker push "$REPO/$svc:staging"

  echo "==> Deploying $svc to Cloud Run"
  gcloud run deploy "$svc" \
    --project "$GCP_PROJECT_ID" \
    --region "$GCP_REGION" \
    --image "$REPO/$svc:$TAG" \
    --quiet
done

AGENT_URL="$(gcloud run services describe agent-service \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --format='value(status.url)')"

echo "==> Smoke test: $AGENT_URL/health"
curl -fsS "$AGENT_URL/health"
echo
echo "==> Deployed. agent-service: $AGENT_URL"
