#!/usr/bin/env bash
set -Eeuo pipefail

CONTAINER_NAME="${BACKEND_CONTAINER_NAME:-qtw-backend}"
IMAGE="${BACKEND_IMAGE:?BACKEND_IMAGE is required}"
ENV_PATH="${DEPLOY_BACKEND_ENV_PATH:-/opt/qtw/backend.env}"
BIND_ADDR="${DEPLOY_BACKEND_BIND:-127.0.0.1}"
HOST_PORT="${DEPLOY_BACKEND_PORT:-8000}"
HEALTH_URL="${DEPLOY_BACKEND_HEALTH_URL:-http://${BIND_ADDR}:${HOST_PORT}/healthz}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 2
  fi
}

container_exists() {
  docker inspect "$CONTAINER_NAME" >/dev/null 2>&1
}

stop_and_remove() {
  if container_exists; then
    docker stop "$CONTAINER_NAME" >/dev/null
    docker rm "$CONTAINER_NAME" >/dev/null
  fi
}

start_container() {
  local image="$1"
  docker run -d \
    --name "$CONTAINER_NAME" \
    --restart unless-stopped \
    --env-file "$ENV_PATH" \
    -p "${BIND_ADDR}:${HOST_PORT}:8000" \
    "$image" >/dev/null
}

check_health() {
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS "$HEALTH_URL" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

require_command docker
require_command curl

if [ ! -f "$ENV_PATH" ]; then
  echo "backend env file not found: $ENV_PATH" >&2
  exit 2
fi

OLD_IMAGE=""
if container_exists; then
  OLD_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER_NAME")"
fi

echo "pulling $IMAGE"
docker pull "$IMAGE"

echo "restarting $CONTAINER_NAME"
stop_and_remove
if ! start_container "$IMAGE"; then
  echo "failed to start new backend container" >&2
  if [ -n "$OLD_IMAGE" ]; then
    echo "rolling back to $OLD_IMAGE" >&2
    start_container "$OLD_IMAGE" || true
  fi
  exit 1
fi

if check_health; then
  echo "backend healthy: $HEALTH_URL"
  exit 0
fi

echo "new backend container failed health check" >&2
docker logs --tail 120 "$CONTAINER_NAME" >&2 || true
stop_and_remove

if [ -n "$OLD_IMAGE" ]; then
  echo "rolling back to $OLD_IMAGE" >&2
  start_container "$OLD_IMAGE"
  if check_health; then
    echo "rollback healthy: $HEALTH_URL" >&2
  else
    echo "rollback failed health check" >&2
    docker logs --tail 120 "$CONTAINER_NAME" >&2 || true
  fi
fi

exit 1
