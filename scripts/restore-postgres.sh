#!/usr/bin/env bash
# Restores the self-hosted Postgres from a backup in GCS — a manual,
# human-invoked runbook step, deliberately never automated. Taking a
# backup (see infrastructure/terraform/scripts/vm-startup.sh.tpl's
# cron job) is safe and additive; restoring OVERWRITES the live
# database, which is exactly the kind of irreversible action this
# project's own risk-tier policy (never auto-execute a CRITICAL action)
# applies to just as much as it does to anything the agent itself does.
#
# Prerequisites:
#   - gcloud CLI authenticated against the target project
#   - psql installed locally
#   - An IAP tunnel to the backing-services VM's Postgres port, since
#     it's firewalled to VPC-internal traffic only (see network.tf):
#       gcloud compute start-iap-tunnel ai-ops-backing-services 5432 \
#         --local-host-port=localhost:15432 --zone="$GCP_ZONE"
#     Run that in a separate terminal and leave it running first.
#
# Usage:
#   ./scripts/restore-postgres.sh --list
#   ./scripts/restore-postgres.sh --backup postgres/aiops-backup-20260101T031700Z.sql.gz
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD to the ai-ops-agent-postgres-password secret value}"
: "${PGHOST:=localhost}"
: "${PGPORT:=15432}"

BUCKET="${GCP_PROJECT_ID}-ai-ops-agent-backups"

if [ "${1:-}" = "--list" ]; then
  gcloud storage ls "gs://$BUCKET/postgres/"
  exit 0
fi

if [ "${1:-}" != "--backup" ] || [ -z "${2:-}" ]; then
  echo "Usage: $0 --list | --backup <object-name>" >&2
  exit 1
fi
BACKUP_OBJECT="$2"

if [ ! -t 0 ]; then
  echo "Refusing to restore: this requires an interactive terminal, not a script" \
    "or scheduled job. This is deliberate — see this file's header comment." >&2
  exit 1
fi

TMP_FILE="$(mktemp /tmp/aiops-restore-XXXXXX.sql.gz)"
trap 'rm -f "$TMP_FILE"' EXIT

echo "==> Downloading gs://$BUCKET/$BACKUP_OBJECT"
gcloud storage cp "gs://$BUCKET/$BACKUP_OBJECT" "$TMP_FILE"

echo
echo "About to REPLACE the live database at $PGHOST:$PGPORT/aiops with:"
echo "  gs://$BUCKET/$BACKUP_OBJECT"
echo "This overwrites all current data — conversations, executions, approvals — with the backup's contents."
read -r -p "Type the backup object's filename (without the postgres/ prefix) to confirm, or anything else to abort: " CONFIRMATION
if [ "$CONFIRMATION" != "$(basename "$BACKUP_OBJECT")" ]; then
  echo "Aborted — no changes made."
  exit 1
fi

echo "==> Restoring"
gunzip -c "$TMP_FILE" | PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U aiops -d aiops

echo "==> Restore complete."
