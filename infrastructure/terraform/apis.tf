# Every API this config's resources actually need enabled on a fresh
# project. Terraform will otherwise fail on the first resource that needs
# one of these, with a less obvious error — enabling them explicitly (and
# first, via depends_on below) makes a from-scratch `terraform apply` work
# in one pass.
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",              # Cloud Run
    "compute.googleapis.com",          # Compute Engine (self-hosted-services VM)
    "artifactregistry.googleapis.com", # Artifact Registry (Docker images)
    "secretmanager.googleapis.com",    # Secret Manager
    "iam.googleapis.com",              # Service accounts
    "iamcredentials.googleapis.com",   # Workload Identity Federation token exchange
    "sts.googleapis.com",              # WIF
    "cloudresourcemanager.googleapis.com",
    "billingbudgets.googleapis.com", # Budget alert (only used if billing_account_id is set)
    "storage.googleapis.com",        # Postgres backups bucket
  ])

  project = var.project_id
  service = each.value

  # Leave the API enabled on `terraform destroy` — disabling it can break
  # other things in the project this config doesn't own, for a resource
  # that costs nothing to leave on.
  disable_on_destroy = false
}
