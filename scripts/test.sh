#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR/agent-service"
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pytest -q "$@"
