#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -f ../.env ]; then
  set -o allexport
  source ../.env
  set +o allexport
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Install Docker and try again."
  exit 1
fi

if ! docker compose -v >/dev/null 2>&1; then
  echo "Docker Compose v2 not found. Install Docker Compose or use Docker Desktop."
  exit 1
fi

echo "Bring up production stack (this may take a few minutes)..."

docker compose -f docker-compose.prod.yml up -d --build

# Wait for health
HOST="https://${IHD_DOMAIN:-yourdomain.com}"
HEALTH_URL="$HOST/api/health"
ATTEMPTS=0
MAX=60

until curl -fsS --insecure "$HEALTH_URL" >/dev/null 2>&1 || [ $ATTEMPTS -ge $MAX ]; do
  ATTEMPTS=$((ATTEMPTS+1))
  echo "Waiting for service ($ATTEMPTS/$MAX)..."
  sleep 2
done

if [ $ATTEMPTS -ge $MAX ]; then
  echo "Service did not respond at $HEALTH_URL within timeout. Check container logs."
  exit 1
fi

echo "Service is up: $HEALTH_URL"
