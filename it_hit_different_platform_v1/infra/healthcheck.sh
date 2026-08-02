#!/usr/bin/env bash
set -euo pipefail

if [ -f ../.env ]; then
  set -o allexport
  source ../.env
  set +o allexport
fi

HOST=${1:-"https://${IHD_DOMAIN:-yourdomain.com}"}

echo "Checking $HOST/api/health"
if curl -fsS "$HOST/api/health" >/dev/null 2>&1; then
  echo "OK"
  exit 0
else
  echo "Healthcheck failed. Use 'docker compose logs caddy' and 'docker compose logs ihd' to inspect."
  exit 2
fi
