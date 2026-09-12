# Cloud Run reaches the self-hosted-services VM's private IP via direct
# VPC egress (network_interfaces on the Cloud Run v2 service, see
# cloud_run.tf) rather than a Serverless VPC Access connector — a
# connector bills for a minimum of 2 always-on instances even at zero
# traffic (a real recurring cost this project doesn't need); direct VPC
# egress only bills for the traffic and the Cloud Run instance itself.

resource "google_compute_network" "main" {
  project                 = var.project_id
  name                    = "ai-ops-agent-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "main" {
  project                  = var.project_id
  name                     = "ai-ops-agent-subnet"
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

# Direct VPC egress reserves addresses for Cloud Run instances out of this
# same subnet, so no separate connector subnet is needed.

# Reserved ahead of the VM itself so secret_manager.tf's DATABASE_URL/
# REDIS_URL/QDRANT_URL values can reference a fixed address rather than
# the VM's own network_ip attribute — the latter would make the secret
# versions depend on the VM while compute.tf's startup script depends on
# those same secrets already existing, a real dependency cycle Terraform
# refuses to plan (confirmed by running `terraform validate`). A static
# address breaks the cycle and, as a bonus, survives the VM being
# recreated without every downstream secret/Cloud Run env needing to
# change too.
resource "google_compute_address" "backing_services_internal" {
  project      = var.project_id
  name         = "ai-ops-backing-services-ip"
  region       = var.region
  subnetwork   = google_compute_subnetwork.main.id
  address_type = "INTERNAL"
}

resource "google_compute_firewall" "allow_internal_to_backing_services" {
  project = var.project_id
  name    = "allow-cloud-run-to-backing-services"
  network = google_compute_network.main.id

  direction     = "INGRESS"
  source_ranges = [google_compute_subnetwork.main.ip_cidr_range]
  target_tags   = ["backing-services"]

  allow {
    protocol = "tcp"
    ports    = ["5432", "6379", "6333", "5678"] # postgres, redis, qdrant, n8n
  }
}

resource "google_compute_firewall" "allow_iap_ssh" {
  project = var.project_id
  name    = "allow-iap-ssh"
  network = google_compute_network.main.id

  direction = "INGRESS"
  # Identity-Aware Proxy's fixed forwarding range — the only source this
  # rule trusts. No SSH key management, no 0.0.0.0/0 port 22.
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["backing-services"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_firewall" "deny_all_other_ingress" {
  project = var.project_id
  name    = "deny-all-other-ingress"
  network = google_compute_network.main.id

  direction     = "INGRESS"
  priority      = 65534
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["backing-services"]

  deny {
    protocol = "all"
  }
}
