# Infrastructure — GCP via Terraform

Deploys the AI-Ops Agent platform to GCP as cheaply as a real deployment
reasonably can be: **no Cloud SQL, no Serverless VPC Access connector, no
Cloud NAT** — the three usual sources of a surprise GCP bill for a
project this size. See "Cost model" below for what that leaves.

## Architecture

```
                    ┌─────────────────────────────┐
  Internet ───────► │  agent-service (Cloud Run)   │──┐
  (its own API-key/ │  scale-to-zero, public       │  │ direct VPC egress
   JWT auth gates   └─────────────────────────────┘  │ (PRIVATE_RANGES_ONLY)
   real access)                                       │
                    ┌─────────────────────────────┐  │
                    │ mock-enterprise (Cloud Run)  │◄─┼── VPC-internal
                    │ scale-to-zero, internal-only │  │   traffic only
                    └─────────────────────────────┘  │
                                                       ▼
                                          ┌─────────────────────────┐
                                          │ backing-services VM      │
                                          │ (e2-micro, Always Free)  │
                                          │ Postgres · Redis · Qdrant│
                                          │ · n8n, via docker compose│
                                          └─────────────────────────┘
```

- **agent-service** and **mock-enterprise** run on Cloud Run
  (`google_cloud_run_v2_service`), scale-to-zero, built from images in
  **Artifact Registry**.
- **Postgres, Redis, Qdrant, and n8n** run as containers on a single
  **e2-micro Compute Engine VM** — the Always Free tier's one perpetually
  free VM, in `us-central1`/`us-east1`/`us-west1` (enforced by
  `variables.tf`'s validation on `var.region`). This is *the* reason
  Cloud SQL isn't used: a managed Postgres instance, even the smallest
  tier, is a real recurring cost; a free VM running Postgres in a
  container is not, at the cost of managing it yourself (backups, patching)
  — an acceptable trade for a portfolio project, explicitly not what
  you'd choose for a real production SLA.
- Cloud Run reaches the VM's private IP via **direct VPC egress**
  (`vpc_access.network_interfaces` on `agent-service`), not a Serverless
  VPC Access connector — a connector bills for a minimum of 2 always-on
  instances even at zero traffic, which alone would cost more than
  everything else in this design combined. Direct VPC egress only bills
  for the Cloud Run instance and its actual traffic.
- The VM keeps its own ephemeral **public IP** (also Always-Free-tier
  covered) purely so its startup script can reach apt/Docker Hub/npm —
  there's no Cloud NAT gateway in this design, which would itself be a
  real recurring cost. Every inbound port except IAP-tunneled SSH
  (`35.235.240.0/20`, see `network.tf`) is firewalled to VPC-internal
  traffic only; the VM is not reachable from the public internet on
  5432/6379/6333/5678 despite having a public IP.
- **Secret Manager** holds every credential (see "Secrets" below);
  nothing is baked into an image or committed.
- **Workload Identity Federation** (`iam.tf`) lets GitHub Actions deploy
  without ever minting a service-account key — Phase 20-21 wires the
  actual CI/CD workflow up to it.

## Cost model

Everything above should cost **$0/month** at low/demo traffic:
Cloud Run's free tier covers light usage at scale-to-zero, Artifact
Registry's free tier covers a handful of images, Secret Manager's free
tier covers far more than the ~11 secrets this config creates, and the
e2-micro VM + its 30GB standard disk + its egress are the specific
resources the Always Free tier exists to cover. Real cost only shows up
from: LLM API usage (Anthropic/OpenAI/Gemini — outside this config
entirely), Cloud Run traffic beyond the free tier, or the VM's own
egress beyond 1GB/month. `billing.tf`'s optional budget alert
(`billing_account_id` + `alert_notification_email`) is there to catch
any of that early — it's an alert, not a spending cap; GCP budgets don't
stop resources on their own.

## What this does NOT do (and why)

- **Does not run `terraform apply`.** This was authored and validated in
  a network-restricted sandbox with no real GCP project or credentials —
  applying it would need both, plus your explicit go-ahead given it
  creates real (if free-tier) billable resources. See "Validating this
  config" below for exactly what *was* verified here versus what you
  still need to do yourself.
- **Does not IAM-gate mock-enterprise to agent-service's specific
  identity.** It relies on `ingress = INGRESS_TRAFFIC_INTERNAL_ONLY`
  (network-level: unreachable from the public internet at all) plus an
  `allUsers` invoker grant, rather than restricting invocation to
  agent-service's service account specifically. The tighter version
  requires agent-service's outbound HTTP client to attach a Cloud Run
  identity token on every call to mock-enterprise — real, worthwhile
  app-code work, deliberately deferred to Phase 20-21 (GCP security
  hardening) rather than done as a drive-by change during this
  infra-focused phase. mock-enterprise has no auth of its own either way
  (it's a self-contained mock with no real data), so the current network
  boundary is a reasonable interim state, not a hidden gap.
- **Does not use a remote (GCS) state backend.** Local state
  (`terraform.tfstate`, git-ignored) avoids bootstrapping and paying for
  a state bucket before Terraform can manage anything else. Fine for one
  maintainer; `versions.tf` has the commented-out `backend "gcs"` block
  ready if this ever needs multi-person/CI-applied state.

## Secrets

Two categories, handled differently (see `secret_manager.tf`'s own
comment for the reasoning):

- **Infra-generated** (Postgres password, JWT signing key, the app's
  `API_KEYS` allowlist, n8n's encryption key/basic-auth password,
  and the derived `DATABASE_URL`/`REDIS_URL`/`QDRANT_URL`): Terraform
  generates these with `random_password` and owns their Secret Manager
  versions end to end. Their values do land in `terraform.tfstate` in
  plaintext — an inherent Terraform limitation for anything it manages
  the value of — which is exactly why local state must never be
  committed and should be handled like a secret itself.
- **Externally-sourced** (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `GOOGLE_API_KEY`): Terraform creates only the empty Secret container.
  Add the real value out-of-band, once, so it never has to pass through
  `terraform apply` or land in state at all:
  ```bash
  printf '%s' 'sk-ant-...' | gcloud secrets versions add ai-ops-agent-anthropic-api-key --data-file=-
  ```
  `terraform apply` prints exactly which secret IDs still need this
  (`external_secrets_needing_a_value` output). **agent-service's Cloud
  Run revision will fail to start** until at least the one matching
  `LLM_PROVIDER` (`anthropic` by default — see `agent-service/.env`) has
  a version.
- The VM fetches its 3 secrets itself at boot, live, via its own service
  account and the Secret Manager REST API (see
  `scripts/vm-startup.sh.tpl`) — never via Terraform-templated instance
  metadata, which anyone with `compute.instances.get` on the VM could
  otherwise read in plaintext.

## Bootstrapping order (chicken-and-egg)

`agent_service_image`/`mock_enterprise_image` default to a Google-hosted
placeholder ("hello") image so `terraform apply` succeeds even before
either image exists — Artifact Registry has to exist before you can push
to it. First apply:

```bash
terraform init
terraform apply                    # creates the (empty) Artifact Registry repo, etc.

# build + push real images (see each service's Dockerfile)
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
docker build -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-ops-agent/agent-service:v1" agent-service/
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-ops-agent/agent-service:v1"
# ...same for mock-enterprise

terraform apply -var agent_service_image=... -var mock_enterprise_image=...
```

Both `google_cloud_run_v2_service` resources have
`lifecycle.ignore_changes` on their image field specifically so that,
after this, a normal CI/CD deploy (`gcloud run deploy` or an Actions
workflow using the Workload Identity Federation this config sets up) can
roll images forward without Terraform reverting them back to whatever
`.tfvars` says on the next `apply` — image tags are a deployment-time
concern, not an infrastructure one.

## Validating this config

Real `terraform validate` (not just eyeballing HCL) against the actual
`hashicorp/google` (5.40.0) and `hashicorp/random` (3.6.3) provider
schemas passed in this sandbox — `registry.terraform.io` itself is
blocked by egress policy here, so the provider binaries were fetched
directly from `releases.hashicorp.com` (HashiCorp's own distribution
point, same artifacts the registry serves) via a filesystem-mirror
`terraform init`. That process caught and fixed one real bug: an actual
circular dependency (`DATABASE_URL` needed the VM's IP; the VM's
`depends_on` needed the secrets to exist first) — fixed by reserving a
static internal IP (`google_compute_address.backing_services_internal`
in `network.tf`) instead of reading the VM's own post-creation IP
attribute. `terraform fmt -check` also passes.

What that *doesn't* cover: an actual `terraform plan`/`apply` against a
real project (needs real GCP credentials this sandbox doesn't have), and
therefore anything only the real API would catch — quota limits,
IAM propagation timing, an org policy this project's account doesn't
know about, etc. Run `terraform plan` yourself before the first real
`apply` and read it.

One lock-file caveat: `.terraform.lock.hcl` (committed, per Terraform's
own recommendation) has checksums for `linux_amd64` only, since the
filesystem-mirror `init` above couldn't reach the registry to fetch the
full multi-platform checksum list. Fine for CI (GitHub Actions' Linux
runners) and any Linux dev machine; on macOS/Windows, run
`terraform init -upgrade` once with real registry access to extend it —
don't hand-edit the file.

## Applying for real

```bash
cp terraform.tfvars.example terraform.tfvars   # fill in project_id, github_repository, etc.
terraform init
terraform plan      # read it
terraform apply
```

Requires a GCP project with billing enabled and credentials with
Owner or an equivalent broad role for the first apply (creating service
accounts, IAM bindings, and enabling APIs all need it); a real
production setup would scope this down to exactly the roles
`apis.tf`/`iam.tf` need and use Workload Identity Federation even for the
human operator's own `apply`, not just CI's.
