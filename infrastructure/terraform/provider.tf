provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  labels = {
    app         = "ai-ops-agent"
    environment = var.environment
    managed_by  = "terraform"
  }
}
