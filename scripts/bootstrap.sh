#!/usr/bin/env bash
# One-time local setup: python venvs + dependency install for both services.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for svc in agent-service mock-enterprise; do
  echo "==> Setting up $svc"
  cd "$ROOT_DIR/$svc"
  [ -d .venv ] || python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip -q
  pip install -r requirements-dev.txt -q
  deactivate
done

[ -f "$ROOT_DIR/.env" ] || cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"

echo "==> Bootstrap complete. Next: make up (docker) or scripts/dev_native.sh (native)"
