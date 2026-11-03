#!/usr/bin/env bash
# Start a local Switch server (v0.31.0) with its bundled Mattermost, then write
# the settings Shield needs to .env. Needs Docker with Compose v2 and git.
#
#   bash scripts/up.sh          # start (first run downloads about 1.6 GB of images)
#   bash scripts/down.sh        # stop and delete the demo data
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SWITCH_DIR="${SWITCH_DIR:-$ROOT/.switch}"
# The Switch commit this project was built and tested against.
SWITCH_COMMIT="${SWITCH_COMMIT:-4e0711a5928340580c3a66e085ecfa550cdcc2eb}"
SWITCH_VERSION="${SWITCH_VERSION:-0.31.0}"
PROJECT="${COMPOSE_PROJECT:-shield}"
API_PORT="${API_PORT:-18000}"
GATEWAY_PORT="${GATEWAY_PORT:-13000}"
MM_PORT="${MM_PORT:-18065}"
PG_PORT="${PG_PORT:-15432}"

if [ ! -d "$SWITCH_DIR/.git" ]; then
  echo "==> Fetching Switch at $SWITCH_COMMIT"
  git init -q "$SWITCH_DIR"
  git -C "$SWITCH_DIR" remote add origin https://github.com/sandbox-quantum/switch.git
  git -C "$SWITCH_DIR" fetch -q --depth 1 origin "$SWITCH_COMMIT"
  git -C "$SWITCH_DIR" checkout -q FETCH_HEAD
fi

cd "$SWITCH_DIR"
if [ ! -f .env ]; then
  echo "==> Generating secrets for a local server"
  cp .env.example .env
  bash deploy/local/generate-env-secrets.sh .env local >/dev/null
fi
sed -i.bak \
  -e "s/^SWITCH_VERSION=.*/SWITCH_VERSION=$SWITCH_VERSION/" \
  -e "s/^API_HOST_PORT=.*/API_HOST_PORT=$API_PORT/" \
  -e "s/^GATEWAY_HOST_PORT=.*/GATEWAY_HOST_PORT=$GATEWAY_PORT/" \
  -e "s/^MATTERMOST_HOST_PORT=.*/MATTERMOST_HOST_PORT=$MM_PORT/" \
  -e "s/^POSTGRES_HOST_PORT=.*/POSTGRES_HOST_PORT=$PG_PORT/" .env && rm -f .env.bak

echo "==> Starting Switch, Postgres, the Gateway and Mattermost (project $PROJECT)"
docker compose -p "$PROJECT" -f deploy/local/standalone-docker-compose.yml --project-directory . \
  --profile collab --profile gateway up -d

echo "==> Waiting for the setup container to link Mattermost"
setup="$(docker compose -p "$PROJECT" -f deploy/local/standalone-docker-compose.yml --project-directory . \
  --profile collab --profile gateway ps -a -q setup)"
code="$(docker wait "$setup")"
if [ "$code" != "0" ]; then
  docker logs "$setup" | tail -20
  echo "Switch setup failed (exit $code)" >&2
  exit 1
fi
for _ in $(seq 1 60); do
  curl -fsS "http://localhost:$API_PORT/health" >/dev/null 2>&1 && break
  sleep 2
done

get() { grep "^$1=" "$SWITCH_DIR/.env" | head -1 | cut -d= -f2-; }
cat > "$ROOT/.env" <<EOF
# Written by scripts/up.sh for a local demo server. Do not commit.
SWITCH_URL=http://localhost:$API_PORT
AGENT_REGISTRATION_TOKEN=$(get AGENT_REGISTRATION_TOKEN)
MATTERMOST_URL=http://localhost:$MM_PORT
MATTERMOST_TEAM=$(get MATTERMOST_TEAM_NAME)
MATTERMOST_USER=$(get MATTERMOST_USER)
MATTERMOST_USER_PASSWORD=$(get MATTERMOST_USER_PASSWORD)
EOF
chmod 600 "$ROOT/.env"
echo "==> Switch is up."
echo "    Mattermost: http://localhost:$MM_PORT  (user: $(get MATTERMOST_USER), password in .env)"
echo "    Next: python -m shield.agent"
