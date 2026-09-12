variable "project_id" {
  description = "GCP project ID. Never hard-coded elsewhere in this config."
  type        = string
}

variable "region" {
  description = "GCP region. Must be us-central1, us-east1, or us-west1 to keep the Compute Engine VM inside the Always Free tier."
  type        = string
  default     = "us-central1"

  validation {
    condition     = contains(["us-central1", "us-east1", "us-west1"], var.region)
    error_message = "Always Free e2-micro is only free in us-central1, us-east1, or us-west1."
  }
}

variable "zone" {
  description = "GCP zone for the self-hosted-services VM."
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "Deployment environment name, propagated into resource labels and the ENVIRONMENT env var."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "This config models exactly the two real GCP environments; local/dev never deploy here."
  }
}

variable "agent_service_image" {
  description = "Full Artifact Registry image reference for agent-service, e.g. REGION-docker.pkg.dev/PROJECT/ai-ops-agent/agent-service:TAG. Left unset on first apply — see README (chicken-and-egg: the repo must exist before an image can be pushed to it)."
  type        = string
  default     = ""
}

variable "mock_enterprise_image" {
  description = "Full Artifact Registry image reference for mock-enterprise. Same chicken-and-egg note as agent_service_image."
  type        = string
  default     = ""
}

variable "vm_machine_type" {
  description = "Machine type for the self-hosted-services VM. e2-micro is the Always Free eligible type; anything larger is a real recurring cost."
  type        = string
  default     = "e2-micro"
}

variable "github_repository" {
  description = "GitHub repo allowed to assume the CI/CD service account via Workload Identity Federation, as \"owner/repo\" (e.g. kalyan-sky/ai-agent). Required for iam.tf's WIF binding to be scoped to this repo only."
  type        = string
}

variable "alert_notification_email" {
  description = "Email address for budget/uptime alert notifications. Optional — leave blank to skip creating a notification channel."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "GCP Billing Budget monthly amount in USD — an alert, not a hard spending cap (GCP budgets don't stop spending on their own)."
  type        = number
  default     = 10
}

variable "billing_account_id" {
  description = "Billing account ID for the budget alert (billingAccounts/XXXXXX-XXXXXX-XXXXXX). Leave blank to skip creating a budget — Terraform needs Billing Account Administrator on this account, a broader permission than everything else in this config needs, so it's opt-in."
  type        = string
  default     = ""
}
