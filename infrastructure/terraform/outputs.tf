output "agent_service_url" {
  description = "Public URL of agent-service. Requires an Authorization: Bearer <api-key> header — see the api-keys secret."
  value       = google_cloud_run_v2_service.agent_service.uri
}

output "mock_enterprise_url" {
  description = "Internal-only URL of mock-enterprise (not reachable from outside the VPC/project)."
  value       = google_cloud_run_v2_service.mock_enterprise.uri
}

output "backing_services_vm_external_ip" {
  description = "Ephemeral external IP of the self-hosted-services VM — for SSH via IAP only; every other port is firewalled to VPC-internal traffic (see network.tf)."
  value       = google_compute_instance.backing_services.network_interface[0].access_config[0].nat_ip
}

output "backing_services_vm_internal_ip" {
  description = "Internal IP Cloud Run reaches Postgres/Redis/Qdrant/n8n on."
  value       = google_compute_instance.backing_services.network_interface[0].network_ip
}

output "artifact_registry_repository" {
  description = "Push images here: REGION-docker.pkg.dev/PROJECT_ID/ai-ops-agent/<service>:<tag>"
  value       = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "github_actions_workload_identity_provider" {
  description = "Full resource name for the GitHub Actions workflow's google-github-actions/auth step (workload_identity_provider input)."
  value       = google_iam_workload_identity_pool_provider.github_actions.name
}

output "github_actions_service_account_email" {
  description = "Service account for the GitHub Actions workflow's google-github-actions/auth step (service_account input)."
  value       = google_service_account.github_actions_ci.email
}

output "postgres_backups_bucket" {
  description = "GCS bucket the VM's nightly backup cron uploads to. Restoring from it is a manual step — see README's 'Backup and restore' section."
  value       = google_storage_bucket.postgres_backups.name
}

output "external_secrets_needing_a_value" {
  description = "Secret IDs created empty — add a real version to each with `gcloud secrets versions add <id> --data-file=-` before deploying (see README)."
  value       = [for id in local.external_secret_ids : google_secret_manager_secret.external[id].secret_id]
}
