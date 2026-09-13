# Three service accounts, none broader than the one job it does:
#   - backing_services_vm: reads exactly the 3 secrets it needs to boot
#     Postgres/n8n, nothing app-related.
#   - agent_service: reads the app secrets Cloud Run needs, and may
#     invoke mock-enterprise's Cloud Run service.
#   - mock_enterprise: no secrets at all — it's a self-contained mock
#     with no external credentials of its own.
# Plus github_actions_ci for Workload Identity Federation (Phase 20-21's
# CI/CD), scoped to exactly one GitHub repo — no service account key ever
# gets minted or downloaded, per CLAUDE.md's WIF-over-long-lived-keys rule.

resource "google_service_account" "backing_services_vm" {
  project      = var.project_id
  account_id   = "ai-ops-backing-services"
  display_name = "AI-Ops Agent — backing-services VM (Postgres/Redis/Qdrant/n8n)"
}

resource "google_service_account" "agent_service" {
  project      = var.project_id
  account_id   = "ai-ops-agent-service"
  display_name = "AI-Ops Agent — agent-service Cloud Run"
}

resource "google_service_account" "mock_enterprise" {
  project      = var.project_id
  account_id   = "ai-ops-mock-enterprise"
  display_name = "AI-Ops Agent — mock-enterprise Cloud Run"
}

resource "google_service_account" "github_actions_ci" {
  project      = var.project_id
  account_id   = "ai-ops-github-actions-ci"
  display_name = "AI-Ops Agent — GitHub Actions CI/CD (Workload Identity Federation)"
}

# --- backing_services_vm: exactly the secrets it needs to boot --------

resource "google_secret_manager_secret_iam_member" "vm_reads_own_secrets" {
  for_each  = toset(["postgres-password", "n8n-encryption-key", "n8n-basic-auth-password"])
  project   = var.project_id
  secret_id = google_secret_manager_secret.infra_generated[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.backing_services_vm.email}"
}

# --- agent_service: app-config secrets + permission to call mock-enterprise

resource "google_secret_manager_secret_iam_member" "agent_service_reads_infra_secrets" {
  for_each  = local.infra_generated_secrets
  project   = var.project_id
  secret_id = google_secret_manager_secret.infra_generated[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_service.email}"
}

resource "google_secret_manager_secret_iam_member" "agent_service_reads_external_secrets" {
  for_each  = toset(local.external_secret_ids)
  project   = var.project_id
  secret_id = google_secret_manager_secret.external[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_service.email}"
}

# mock-enterprise's invoker policy (scoped to agent_service's own service
# account, not allUsers) lives in cloud_run.tf next to its ingress
# setting and the env var that makes agent-service actually present a
# matching identity token.

# --- Artifact Registry: both Cloud Run services need to pull their image

resource "google_artifact_registry_repository_iam_member" "agent_service_pulls_images" {
  project    = var.project_id
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.agent_service.email}"
}

resource "google_artifact_registry_repository_iam_member" "mock_enterprise_pulls_images" {
  project    = var.project_id
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.mock_enterprise.email}"
}

# --- Workload Identity Federation for GitHub Actions -------------------
# No JSON key ever created or downloaded: GitHub's own OIDC token is
# exchanged for short-lived GCP credentials, scoped to this one repo.

resource "google_iam_workload_identity_pool" "github_actions" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github_actions" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  # Scoped to exactly this repo — any other GitHub repo's OIDC token,
  # even from the same GitHub org, is rejected at the token-exchange step.
  attribute_condition = "assertion.repository == \"${var.github_repository}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_actions_can_impersonate" {
  service_account_id = google_service_account.github_actions_ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "github_actions_deploys_cloud_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.github_actions_ci.email}"
}

resource "google_artifact_registry_repository_iam_member" "github_actions_pushes_images" {
  project    = var.project_id
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_actions_ci.email}"
}

resource "google_service_account_iam_member" "github_actions_acts_as_runtime_sas" {
  for_each = {
    agent_service   = google_service_account.agent_service.name
    mock_enterprise = google_service_account.mock_enterprise.name
  }

  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions_ci.email}"
}
