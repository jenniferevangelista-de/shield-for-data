#!/usr/bin/env bash
# Stop the local Switch server and delete its data and Shield's demo state.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SWITCH_DIR="${SWITCH_DIR:-$ROOT/.switch}"
cd "$SWITCH_DIR"
docker compose -p "${COMPOSE_PROJECT:-shield}" -f deploy/local/standalone-docker-compose.yml \
  --project-directory . --profile collab --profile gateway down -v
rm -rf "$ROOT/.shield"
echo "Stopped. Run scripts/up.sh to start again."
