# The one Compute Engine VM this project runs: self-hosted Postgres,
# Redis, Qdrant, and n8n — the pieces this project deliberately keeps off
# Cloud SQL / managed equivalents to avoid their cost (see CLAUDE.md).
# e2-micro in us-central1/us-east1/us-west1 (enforced by variables.tf's
# validation on var.region) is Always Free tier eligible: this VM, on its
# own, should cost nothing to run continuously.

resource "google_compute_instance" "backing_services" {
  project      = var.project_id
  name         = "ai-ops-backing-services"
  machine_type = var.vm_machine_type
  zone         = var.zone
  labels       = local.labels
  tags         = ["backing-services"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      # 30GB is the largest standard-persistent-disk size still covered
      # by the Always Free allowance; more than this project's few
      # containers + volumes need, but free is free.
      size = 30
      type = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.main.id
    network_ip = google_compute_address.backing_services_internal.address
    # Always Free's e2-micro offer includes this ephemeral external IP —
    # needed for the startup script's own apt/Docker Hub/npm pulls
    # (there's no NAT gateway in this design; adding one to avoid a
    # public IP would itself be a real recurring cost). Inbound traffic
    # to it is still locked down entirely by network.tf's firewall rules.
    access_config {}
  }

  service_account {
    email  = google_service_account.backing_services_vm.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile("${path.module}/scripts/vm-startup.sh.tpl", {
      project_id    = var.project_id
      backup_bucket = google_storage_bucket.postgres_backups.name
    })
  }

  allow_stopping_for_update = true

  # Deliberately no depends_on for the secret versions: the startup
  # script fetches them live over HTTPS at boot (see the script itself),
  # not via Terraform interpolation, so there's no create-order
  # requirement here — and adding one previously caused the exact cycle
  # this file's network_ip comment explains.
  depends_on = [google_project_service.apis]
}
