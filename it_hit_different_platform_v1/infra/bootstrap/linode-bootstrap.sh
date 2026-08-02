#!/usr/bin/env bash
set -euo pipefail

REPO_URL=${1:-}
IHD_DOMAIN=${2:-}
IH_USER=${3:-ihdadmin}
IHD_DIR=${4:-/opt/ihd}

if [ -z "$REPO_URL" ] || [ -z "$IHD_DOMAIN" ]; then
  cat >&2 <<EOF
Usage: $0 <git-repo-url> <IHD_DOMAIN> [user] [install-dir]
Example: $0 https://github.com/you/ihd.git ihd.example.com ihdadmin /opt/ihd
EOF
  exit 1
fi

echo "Bootstrap start: REPO_URL=$REPO_URL IHD_DOMAIN=$IHD_DOMAIN IH_USER=$IH_USER IHD_DIR=$IHD_DIR"

# Update & base packages
apt update
apt upgrade -y
apt install -y git curl sudo ufw

# Create non-root user if needed
if ! id -u "$IH_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$IH_USER"
  usermod -aG sudo "$IH_USER"
fi

# Install Docker (official convenience script)
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sh /tmp/get-docker.sh
  rm -f /tmp/get-docker.sh
fi

# Install docker compose plugin
if ! docker compose version >/dev/null 2>&1; then
  apt update
  apt install -y docker-compose-plugin
fi

# Ensure user can run docker (requires re-login to take effect)
usermod -aG docker "$IH_USER" || true

# Clone repository or copy local source
if [ -d "$IHD_DIR" ]; then
  echo "Removing existing $IHD_DIR"
  rm -rf "$IHD_DIR"
fi
if [ -d "$REPO_URL" ]; then
  echo "Copying local source from $REPO_URL to $IHD_DIR"
  mkdir -p "$IHD_DIR"
  cp -a "$REPO_URL"/. "$IHD_DIR/"
else
  echo "Cloning repository from $REPO_URL"
  git clone "$REPO_URL" "$IHD_DIR"
fi
chown -R "$IH_USER":"$IH_USER" "$IHD_DIR"

# Prepare .env
if [ -f "$IHD_DIR/.env" ]; then
  echo ".env already exists, leaving it in place"
else
  if [ -f "$IHD_DIR/.env.example" ]; then
    cp "$IHD_DIR/.env.example" "$IHD_DIR/.env"
    if grep -qE "^IHD_DOMAIN=" "$IHD_DIR/.env"; then
      sed -i -E "s/^IHD_DOMAIN=.*/IHD_DOMAIN=${IHD_DOMAIN}/" "$IHD_DIR/.env"
    else
      echo "IHD_DOMAIN=${IHD_DOMAIN}" >> "$IHD_DIR/.env"
    fi

    # Ensure production-safe defaults are present
    if ! grep -qE "^IHD_SECURE_COOKIE=" "$IHD_DIR/.env"; then
      echo "IHD_SECURE_COOKIE=1" >> "$IHD_DIR/.env"
    fi
    if ! grep -qE "^IHD_STUN_URL=" "$IHD_DIR/.env"; then
      echo "IHD_STUN_URL=stun:turn.${IHD_DOMAIN}:3478" >> "$IHD_DIR/.env"
    fi
    if ! grep -qE "^IHD_TURN_URL=" "$IHD_DIR/.env"; then
      echo "IHD_TURN_URL=turn:${IHD_DOMAIN}:3478" >> "$IHD_DIR/.env"
    fi
    if ! grep -qE "^IHD_TURN_USERNAME=" "$IHD_DIR/.env"; then
      echo "IHD_TURN_USERNAME=ihd-user" >> "$IHD_DIR/.env"
    fi
    if ! grep -qE "^IHD_TURN_PASSWORD=" "$IHD_DIR/.env"; then
      echo "IHD_TURN_PASSWORD=CHANGE_ME" >> "$IHD_DIR/.env"
    fi
    if ! grep -qE "^IHD_HOST=" "$IHD_DIR/.env"; then
      echo "IHD_HOST=0.0.0.0" >> "$IHD_DIR/.env"
    fi
    if ! grep -qE "^IHD_PORT=" "$IHD_DIR/.env"; then
      echo "IHD_PORT=8787" >> "$IHD_DIR/.env"
    fi
    if ! grep -qE "^POSTGRES_DB=" "$IHD_DIR/.env"; then
      echo "POSTGRES_DB=ihd" >> "$IHD_DIR/.env"
    fi

    chown "$IH_USER":"$IH_USER" "$IHD_DIR/.env"
    echo "Created .env and set IHD_DOMAIN=${IHD_DOMAIN}"
  else
    echo "Warning: .env.example not found; creating minimal .env"
    cat > "$IHD_DIR/.env" <<EOF
IHD_DOMAIN=${IHD_DOMAIN}
EOF
    chown "$IH_USER":"$IH_USER" "$IHD_DIR/.env"
  fi
fi

# Firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
# If you plan to run TURN uncomment:
# ufw allow 3478/udp
ufw --force enable

# Start the Docker Compose stack (as root to avoid needing re-login)
if [ -f "$IHD_DIR/infra/docker-compose.prod.yml" ]; then
  docker compose -f "$IHD_DIR/infra/docker-compose.prod.yml" up -d --build
else
  echo "docker-compose.prod.yml not found in $IHD_DIR/infra - attempting example compose"
  if [ -f "$IHD_DIR/infra/docker-compose.caddy.example.yml" ]; then
    docker compose -f "$IHD_DIR/infra/docker-compose.caddy.example.yml" up -d --build
  else
    echo "No compose file found; please run docker compose manually in $IHD_DIR/infra"
    exit 1
  fi
fi

echo "Bootstrap finished. Check https://${IHD_DOMAIN}/api/health and container logs:"
echo "  docker ps"
echo "  docker compose -f $IHD_DIR/infra/docker-compose.prod.yml logs -f --tail=200"
