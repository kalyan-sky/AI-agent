#!/usr/bin/env bash
# Seeds the mock-enterprise API with a demo-friendly mix of scenarios across
# several services, so a walkthrough has more than just payment-service's
# (already-default) failed-deployment scenario to look at.
set -euo pipefail

BASE_URL="${MOCK_ENTERPRISE_BASE_URL:-http://127.0.0.1:9000}"

seed() {
  local service="$1" scenario="$2"
  curl -sS -X POST "$BASE_URL/admin/scenarios/$service" \
    -H "Content-Type: application/json" \
    -d "{\"scenario\": \"$scenario\"}" | python3 -m json.tool
}

echo "==> Seeding demo scenarios against $BASE_URL"
seed payment-service failed_deployment
seed checkout-service database_outage
seed inventory-service api_timeout
seed notifications-service high_latency
seed auth-gateway auth_failure
seed search-service healthy

echo "==> Done. Verify with: curl $BASE_URL/services/payment-service/health"
