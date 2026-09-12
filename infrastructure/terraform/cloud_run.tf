# Direct VPC egress (network_interfaces below) instead of a Serverless
# VPC Access connector — see network.tf's comment for why: a connector
# has a real always-on minimum cost this project doesn't need.

resource "google_cloud_run_v2_service" "mock_enterprise" {
  project  = var.project_id
  name     = "mock-enterprise"
  location = var.region
  labels   = local.labels

  # Never reachable from the public internet — only from inside this
  # project's VPC or from another Cloud Run service in the same project —
  # AND, per the invoker binding below, only from agent-service's own
  # service account specifically: agent-service's outbound HTTP client
  # (app/tools/http.py) attaches a Cloud Run identity token to every call
  # here when GCP_ID_TOKEN_AUDIENCE is set (see this service's own env
  # block below), so this is real identity-based auth, not just a network
  # boundary — mock-enterprise has no app-level auth of its own either
  # way, being a self-contained mock with no real data.
  ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.mock_enterprise.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.mock_enterprise_image != "" ? var.mock_enterprise_image : "us-docker.pkg.dev/cloudrun/container/hello"

      ports {
        container_port = 9000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "256Mi"
        }
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }
    }
  }

  depends_on = [google_project_service.apis]

  lifecycle {
    # Once a real image has been pushed and deployed once (by CI or a
    # manual `gcloud run deploy`), Terraform should stop fighting over
    # which image tag is "current" — that's a deployment-time concern,
    # not an infra one. Applies to both services below too.
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service_iam_member" "mock_enterprise_allow_agent_service" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mock_enterprise.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.agent_service.email}"
}

resource "google_cloud_run_v2_service" "agent_service" {
  project  = var.project_id
  name     = "agent-service"
  location = var.region
  labels   = local.labels

  # Public ingress by design: this service's own API-key/JWT + RBAC layer
  # (app/security/) is the real access control, sent as a normal
  # `Authorization: Bearer <key>` header — the same header slot Cloud
  # Run's own IAM auth would need for a Google-signed ID token, so the
  # two schemes can't be layered here without changing how every existing
  # caller (n8n's custom node included) authenticates.
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.agent_service.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.main.id
        subnetwork = google_compute_subnetwork.main.id
      }
      # Only route VPC-internal-range traffic through the VPC interface;
      # calls to api.anthropic.com etc. still go straight out to the
      # public internet the normal (free, simple) way.
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.agent_service_image != "" ? var.agent_service_image : "us-docker.pkg.dev/cloudrun/container/hello"

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "MOCK_ENTERPRISE_BASE_URL"
        value = google_cloud_run_v2_service.mock_enterprise.uri
      }
      env {
        # A Cloud Run identity token's audience must exactly match the
        # target service's own URL — mock-enterprise's invoker IAM
        # binding above only accepts a token issued for this audience.
        name  = "GCP_ID_TOKEN_AUDIENCE"
        value = google_cloud_run_v2_service.mock_enterprise.uri
      }

      # Only the secrets agent-service's own config.py actually reads —
      # postgres-password (folded into database-url already), and n8n's
      # two secrets, are deliberately excluded rather than passed as
      # unused env vars.
      dynamic "env" {
        for_each = {
          JWT_SECRET_KEY = google_secret_manager_secret.infra_generated["jwt-secret-key"].secret_id
          API_KEYS       = google_secret_manager_secret.infra_generated["api-keys"].secret_id
          DATABASE_URL   = google_secret_manager_secret.infra_generated["database-url"].secret_id
          REDIS_URL      = google_secret_manager_secret.infra_generated["redis-url"].secret_id
          QDRANT_URL     = google_secret_manager_secret.infra_generated["qdrant-url"].secret_id
        }
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      dynamic "env" {
        for_each = {
          ANTHROPIC_API_KEY = google_secret_manager_secret.external["anthropic-api-key"].secret_id
          OPENAI_API_KEY    = google_secret_manager_secret.external["openai-api-key"].secret_id
          GOOGLE_API_KEY    = google_secret_manager_secret.external["google-api-key"].secret_id
        }
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_project_service.apis]

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_cloud_run_v2_service_iam_member" "agent_service_allow_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
