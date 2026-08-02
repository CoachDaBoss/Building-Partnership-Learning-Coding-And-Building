# Linode Bootstrap

This folder contains a bootstrap script for setting up the IHD app on a fresh Linode.

## Usage

### Option A: GitHub repository available

```bash
curl -fsSL "https://raw.githubusercontent.com/<your-github-user>/<your-repo>/main/infra/bootstrap/linode-bootstrap.sh" | sudo bash -s -- "https://github.com/<your-github-user>/<your-repo>.git" "ihd.example.com"
```

### Option B: Local source copy (no GitHub required)

1. Copy the source files to the Linode.

```bash
scp -r . root@<LINODE_IP>:/opt/ihd-source
scp infra/bootstrap/linode-bootstrap.sh root@<LINODE_IP>:/tmp/
```

2. Run the bootstrap script on the Linode.

```bash
ssh root@<LINODE_IP>
bash /tmp/linode-bootstrap.sh "/opt/ihd-source" "ihd.example.com"
```

### After bootstrap

- If `/opt/ihd/.env` does not exist, copy the example file:

```bash
cd /opt/ihd
cp .env.example .env
```

- Edit `/opt/ihd/.env` and set:
  - `IHD_DOMAIN` to your public hostname
  - `IHD_MASTER_EMAIL`
  - `IHD_MASTER_PASSWORD`
  - `POSTGRES_PASSWORD`
  - `MINIO_ROOT_PASSWORD`
  - `IHD_TURN_PASSWORD` (if using TURN)
  - `IHD_SECURE_COOKIE=1`

- Start the stack manually if needed:

```bash
cd /opt/ihd/infra
docker compose -f docker-compose.prod.yml up -d --build
```

- If `.env` already exists, the bootstrap script leaves it in place.

### Optional systemd service

Copy the provided systemd unit file to `/etc/systemd/system/ihd-docker-compose.service`:

```bash
sudo cp infra/bootstrap/ihd-docker-compose.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ihd-docker-compose.service
```

### Notes

- The bootstrap script installs Docker, the Docker Compose plugin, creates a user, clones or copies source, enables UFW for ports 22/80/443, and launches the stack.
- If you use TURN, also allow `3478/udp` in UFW.
