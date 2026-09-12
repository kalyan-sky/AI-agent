resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "ai-ops-agent"
  format        = "DOCKER"
  description   = "agent-service and mock-enterprise container images"
  labels        = local.labels

  # Keeps the repo small (and storage cost near zero) by default: 5
  # newest tagged versions per image kept, everything else past 14 days
  # old cleaned up automatically. A real rollback target should be
  # re-tagged (e.g. "stable") rather than relying on an untagged digest
  # surviving cleanup.
  cleanup_policies {
    id     = "keep-latest-5-tagged"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }

  cleanup_policies {
    id     = "delete-untagged-after-14d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "1209600s" # 14 days
    }
  }

  depends_on = [google_project_service.apis]
}
