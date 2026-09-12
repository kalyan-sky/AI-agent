# Two categories of secret, deliberately handled differently:
#
# 1. Infra-generated (Postgres password, JWT signing key, n8n's own
#    secrets, the app's API-key allowlist): nothing outside this config
#    could supply them, so Terraform generates and owns them end to end.
#    Their values do end up in terraform.tfstate in plaintext — an
#    inherent Terraform limitation for anything it manages the value of,
#    not something Secret Manager changes — which is exactly why local
#    state must never be committed (see versions.tf) and should be
#    treated as sensitive as the secrets themselves.
#
# 2. Externally-sourced (LLM provider API keys): Terraform creates only
#    the empty Secret container below. The real key value is added
#    out-of-band with `gcloud secrets versions add` (see README) so it
#    never has to pass through a `terraform apply` or land in state at
#    all — the stronger guarantee, worth the one extra manual step for a
#    value Terraform has no legitimate way to generate itself anyway.

resource "random_password" "postgres_password" {
  length  = 32
  special = false
}

resource "random_password" "jwt_secret_key" {
  length  = 48
  special = false
}

resource "random_password" "n8n_encryption_key" {
  length  = 32
  special = false
}

resource "random_password" "n8n_basic_auth_password" {
  length  = 24
  special = false
}

resource "random_password" "api_key_viewer" {
  length  = 32
  special = false
}

resource "random_password" "api_key_operator" {
  length  = 32
  special = false
}

resource "random_password" "api_key_admin" {
  length  = 32
  special = false
}

locals {
  # Format app/security/api_key.py expects: "key1:role1,key2:role2".
  api_keys_value = join(",", [
    "${random_password.api_key_viewer.result}:viewer",
    "${random_password.api_key_operator.result}:operator",
    "${random_password.api_key_admin.result}:admin",
  ])

  database_url_value = "postgresql+asyncpg://aiops:${random_password.postgres_password.result}@${google_compute_address.backing_services_internal.address}:5432/aiops"
  redis_url_value    = "redis://${google_compute_address.backing_services_internal.address}:6379/0"
  qdrant_url_value   = "http://${google_compute_address.backing_services_internal.address}:6333"

  infra_generated_secrets = {
    postgres-password       = random_password.postgres_password.result
    jwt-secret-key          = random_password.jwt_secret_key.result
    api-keys                = local.api_keys_value
    database-url            = local.database_url_value
    redis-url               = local.redis_url_value
    qdrant-url              = local.qdrant_url_value
    n8n-encryption-key      = random_password.n8n_encryption_key.result
    n8n-basic-auth-password = random_password.n8n_basic_auth_password.result
  }

  external_secret_ids = [
    "anthropic-api-key",
    "openai-api-key",
    "google-api-key",
  ]
}

resource "google_secret_manager_secret" "infra_generated" {
  for_each  = local.infra_generated_secrets
  project   = var.project_id
  secret_id = "ai-ops-agent-${each.key}"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "infra_generated" {
  for_each    = local.infra_generated_secrets
  secret      = google_secret_manager_secret.infra_generated[each.key].id
  secret_data = each.value
}

resource "google_secret_manager_secret" "external" {
  for_each  = toset(local.external_secret_ids)
  project   = var.project_id
  secret_id = "ai-ops-agent-${each.key}"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}
