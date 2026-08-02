# IHD Docs Summary

This document summarizes the repository's main documentation and deployment guides.

## Key documentation files

### `README.md`
- Primary app overview and MVP feature list.
- Local launch instructions for Windows and Linux.
- LAN testing guidance and HTTPS warning for media devices.
- Container deployment with `infra/docker-compose.prod.yml`, `infra/caddy/Caddyfile`, and `.env.example`.
- Deployer script usage: `./deploy.sh` and remote deploy examples.
- Cloudflare checklist and TLS troubleshooting notes.
- Production readiness checklist and security recommendations.

### `infra/README.md`
- Infrastructure-specific deployment guide for the production Docker stack.
- Lists included infra files and utilities.
- Quick start for `docker compose -f infra/docker-compose.prod.yml up -d --build`.
- Requires `.env` values: `IHD_DOMAIN`, admin credentials, Postgres/MinIO secrets, TURN secrets, `IHD_SECURE_COOKIE=1`.
- Healthcheck command and Cloudflare proxy guidelines.
- Notes on Caddy using `IHD_DOMAIN` and preventing public exposure of port `8787`.

### `infra/bootstrap/README.md`
- Linode bootstrap usage for GitHub-hosted or local source deployments.
- Commands for copying source and running `linode-bootstrap.sh`.
- Post-bootstrap `.env` instructions and manual startup steps.
- Optional systemd service installation instructions.
- Notes on Docker install, UFW setup, and bootstrap behavior.

### `docs/DEPLOYMENT.md`
- Deployment guidance for private VPS and HTTPS reverse proxy patterns.
- Containerized deployment examples with Caddy and Docker Compose.
- Cloudflare and proxy/TLS checklists.
- Live session TURN/STUN environment guidance.
- Backup command for local `data/` directory.

### `docs/LEGAL_PRODUCT_BOUNDARIES.md`
- Legal/product boundary guidance for copyright, business education, referrals, and privacy.
- Emphasizes avoiding unauthorized legal/tax/accounting advice.
- Recommends counsel-reviewed policies and proper dispute handling.

### `docs/PRODUCTION_ROADMAP.md`
- Product roadmap from MVP through pro studio features, private infrastructure, scalable live sessions, rights/royalties operations, distribution integrations, and desktop/mobile companion apps.

## Deployment helper

### `deploy.sh`
- Local and remote deploy helper that uses `docker compose -f infra/docker-compose.prod.yml up -d --build`.
- Remote deploy support via `--host` and `--dir` with `rsync` and SSH.
- Includes Cloudflare and TLS proxy checklist guidance.
- Enforces secure proxy deployment and avoids direct public exposure of internal app ports.

## What is ready
- Complete end-to-end deployment documentation exists in the repo.
- Infra and bootstrap docs cover production launch and Cloudflare-based HTTPS deployment.
- A deployer script is available for local and remote use.
- Additional docs cover legal boundaries and product roadmap.

## Recommended next steps
1. Provision a public origin server or VPS.
2. Copy the repository and create `.env` with `IHD_DOMAIN`, credentials, and secrets.
3. Run `docker compose -f infra/docker-compose.prod.yml up -d --build`.
4. Configure Cloudflare or another proxy to point the public hostname to the origin.
5. Verify `https://<IHD_DOMAIN>/api/health` and confirm TLS is valid for the public domain.
