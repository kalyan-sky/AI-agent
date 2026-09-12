#!/usr/bin/env bash
# Runs on every boot (GCE re-runs the startup-script metadata key on
# every restart, not just the first) — every step below is written to be
# safe to repeat rather than assuming a fresh machine.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg jq
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# Secrets are fetched at boot via this VM's own service account — never
# baked into instance metadata or this script, which anyone with
# compute.instances.get on this VM could otherwise read.
ACCESS_TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | jq -r '.access_token')

fetch_secret() {
  curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
    "https://secretmanager.googleapis.com/v1/projects/${project_id}/secrets/$1/versions/latest:access" \
    | jq -r '.payload.data' | base64 -d
}

POSTGRES_PASSWORD="$(fetch_secret ai-ops-agent-postgres-password)"
N8N_ENCRYPTION_KEY="$(fetch_secret ai-ops-agent-n8n-encryption-key)"
N8N_BASIC_AUTH_PASSWORD="$(fetch_secret ai-ops-agent-n8n-basic-auth-password)"

mkdir -p /opt/ai-ops-agent
cat > /opt/ai-ops-agent/.env <<EOF
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
N8N_ENCRYPTION_KEY=$N8N_ENCRYPTION_KEY
N8N_BASIC_AUTH_PASSWORD=$N8N_BASIC_AUTH_PASSWORD
EOF
chmod 600 /opt/ai-ops-agent/.env

cat > /opt/ai-ops-agent/docker-compose.yml <<'COMPOSE'
name: ai-ops-agent-backing-services

networks:
  aiops-net:

volumes:
  pgdata:
  qdrant_storage:
  n8n_data:

services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: aiops
      POSTGRES_USER: aiops
      POSTGRES_PASSWORD: $${POSTGRES_PASSWORD}
    volumes: ["pgdata:/var/lib/postgresql/data"]
    ports: ["5432:5432"]
    networks: [aiops-net]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aiops -d aiops"]
      interval: 10s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    ports: ["6379:6379"]
    networks: [aiops-net]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10

  qdrant:
    image: qdrant/qdrant:v1.11.0
    restart: unless-stopped
    volumes: ["qdrant_storage:/qdrant/storage"]
    ports: ["6333:6333"]
    networks: [aiops-net]

  n8n:
    image: n8nio/n8n:1.61.0
    restart: unless-stopped
    environment:
      N8N_BASIC_AUTH_ACTIVE: "true"
      N8N_BASIC_AUTH_USER: admin
      N8N_BASIC_AUTH_PASSWORD: $${N8N_BASIC_AUTH_PASSWORD}
      N8N_ENCRYPTION_KEY: $${N8N_ENCRYPTION_KEY}
      N8N_PORT: "5678"
      N8N_PROTOCOL: http
      GENERIC_TIMEZONE: UTC
    volumes: ["n8n_data:/home/node/.n8n"]
    ports: ["5678:5678"]
    networks: [aiops-net]
COMPOSE

cd /opt/ai-ops-agent
docker compose up -d
