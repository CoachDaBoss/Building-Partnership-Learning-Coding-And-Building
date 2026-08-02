#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$REPO_ROOT/.env"
COMPOSE_FILE="$REPO_ROOT/infra/docker-compose.prod.yml"

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Deploy the IHD app locally or to a remote host.

Options:
  --host HOST          Remote SSH host to deploy to (optional)
  --dir DIR            Remote install directory (default: /opt/ihd)
  --port PORT          SSH port for remote host (default: 22)
  --healthcheck        Run the remote health check after deployment
  --help               Show this help message

Examples:
  # Deploy locally from the repo root
  ./deploy.sh

  # Deploy to a remote server
  ./deploy.sh --host root@1.2.3.4 --dir /opt/ihd
EOF
}

REMOTE_HOST=""
REMOTE_DIR="/opt/ihd"
SSH_PORT=22
RUN_HEALTHCHECK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --dir)
      REMOTE_DIR="$2"
      shift 2
      ;;
    --port)
      SSH_PORT="$2"
      shift 2
      ;;
    --healthcheck)
      RUN_HEALTHCHECK=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

if [ ! -f "$ENV_FILE" ]; then
  echo ".env not found in repository root. Copy .env.example to .env and edit it before deploying."
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Compose file not found: $COMPOSE_FILE"
  exit 1
fi

if [ -n "$REMOTE_HOST" ]; then
  echo "Deploying to remote host $REMOTE_HOST into $REMOTE_DIR"
  rsync -av --delete \
    --exclude '.git' \
    --exclude 'deployment_bundle.zip' \
    --exclude 'data' \
    --exclude '__pycache__' \
    "$REPO_ROOT/" "$REMOTE_HOST:$REMOTE_DIR/"

  ssh -p "$SSH_PORT" "$REMOTE_HOST" <<EOF
set -euo pipefail
cd '$REMOTE_DIR/infra'
if [ ! -f '../.env' ]; then
  echo '.env missing on remote host. Ensure .env exists in $REMOTE_DIR before deploying.'
  exit 1
fi
/usr/bin/docker compose -f docker-compose.prod.yml up -d --build
EOF

  if [ "$RUN_HEALTHCHECK" -eq 1 ]; then
    ssh -p "$SSH_PORT" "$REMOTE_HOST" "cd '$REMOTE_DIR/infra' && ./healthcheck.sh"
  fi
else
  echo "Deploying locally"
  cd "$REPO_ROOT/infra"
  docker compose -f docker-compose.prod.yml up -d --build
  if [ "$RUN_HEALTHCHECK" -eq 1 ]; then
    ./healthcheck.sh
  fi
fi

echo "Deployment completed."
