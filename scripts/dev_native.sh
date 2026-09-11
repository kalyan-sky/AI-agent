#!/usr/bin/env bash
# Starts the platform using native processes instead of Docker Compose.
#
# This exists for network-restricted environments (e.g. sandboxes that block
# Docker Hub image pulls) where `docker compose up` cannot pull postgres/
# redis/qdrant/n8n images. It requires PostgreSQL and Redis installed via the
# system package manager (`apt-get install postgresql redis-server`), and
# uses Qdrant's embedded local-mode client (no server process) via
# QDRANT_LOCAL_PATH in agent-service/.env. n8n is NOT started by this script
# — n8n's dependency tree pulls at least one asset from a CDN that most
# restrictive egress policies block, so it should be run via
# `docker compose up n8n` (or `npx n8n`) in a normal-network environment.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Starting PostgreSQL"
service postgresql start || pg_ctlcluster 16 main start

echo "==> Starting Redis"
redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes --port 6379

echo "==> Starting mock-enterprise API on :9000"
cd "$ROOT_DIR/mock-enterprise"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
setsid nohup uvicorn app.main:app --host 0.0.0.0 --port 9000 > /tmp/mock-enterprise.log 2>&1 < /dev/null &
disown
deactivate

echo "==> Starting agent-service API on :8000"
cd "$ROOT_DIR/agent-service"
[ -d .venv ] || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
setsid nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir . > /tmp/agent-service.log 2>&1 < /dev/null &
disown
deactivate

sleep 2
echo "==> Health checks"
curl -sS http://127.0.0.1:9000/health && echo
curl -sS http://127.0.0.1:8000/health && echo
curl -sS http://127.0.0.1:8000/ready && echo
