terraform {
  required_version = ">= 1.9.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Local state on purpose: a remote (GCS) backend is the right call for a
  # real team, but it means paying for a bucket and bootstrapping it before
  # Terraform can manage anything else — overhead this single-maintainer,
  # cost-conscious project doesn't need yet. terraform.tfstate is
  # git-ignored (see repo root .gitignore); switching to a GCS backend
  # later is an additive change here, not a rewrite.
  # backend "gcs" {
  #   bucket = "REPLACE-ME-tfstate-bucket"
  #   prefix = "ai-ops-agent"
  # }
}
