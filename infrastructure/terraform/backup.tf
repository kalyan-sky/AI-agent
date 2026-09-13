# Automated Postgres backups — the VM's cron job (see scripts/vm-startup.sh.tpl)
# uploads here nightly. Restoring FROM here is a separate, deliberately
# manual step (scripts/restore-postgres.sh, run by a human operator) —
# see infrastructure/terraform/README.md's "Backup and restore" section
# for why: taking a backup is safe/additive, but restoring overwrites the
# live database, which is exactly the kind of irreversible action this
# project's whole risk-tier policy says should never be automated.

resource "google_storage_bucket" "postgres_backups" {
  project                     = var.project_id
  name                        = "${var.project_id}-ai-ops-agent-backups"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  labels                      = local.labels

  # 30 days is enough to recover from "the VM died" or "a bad migration
  # corrupted data last week" without the bucket growing without bound —
  # small Postgres dumps at this project's scale should stay well within
  # GCS's Always Free tier (5GB-months) regardless, but a lifecycle rule
  # means that stays true even if nightly backups run for years.
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  # Old object versions could otherwise survive past the age rule above
  # if versioning were ever turned on; it isn't, but this keeps the
  # bucket's behavior unambiguous either way.
  versioning {
    enabled = false
  }

  depends_on = [google_project_service.apis]
}

# Write-only, and only to this one bucket: the VM can add a new backup
# but cannot read, overwrite, or delete an existing one — so a compromised
# VM can't use its own credentials to tamper with backups made before the
# compromise. Restoring (reading) is a human operator's own gcloud/IAM
# access, granted outside this Terraform config, not this service account's.
resource "google_storage_bucket_iam_member" "vm_writes_backups" {
  bucket = google_storage_bucket.postgres_backups.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.backing_services_vm.email}"
}
