# IHD Infrastructure

This folder contains the production Docker Compose stack and Caddy reverse proxy configuration for the IHD app.

## Included files

- `Dockerfile` — builds the Python app container from the repository root.
- `docker-compose.prod.yml` — production-ready stack with Postgres, Redis, MinIO, LiveKit, coturn, app container, and Caddy.
- `docker-compose.caddy.example.yml` — minimal reverse-proxy example for local HTTPS testing.
- `caddy/Caddyfile` — Caddy configuration that uses `IHD_DOMAIN` from the shared `.env`.
- `start_prod.sh` — helper script to start the production stack using `docker compose`.
- `healthcheck.sh` — helper script to verify the public domain health endpoint.

## Quick start

1. Copy `.env.example` to `.env` at the repo root.
2. Edit `.env` and set:
   - `IHD_DOMAIN`
   - `IHD_MASTER_EMAIL`
   - `IHD_MASTER_PASSWORD`
   - `POSTGRES_PASSWORD`
   - `MINIO_ROOT_PASSWORD`
   - `IHD_TURN_PASSWORD` (if using TURN)
   - `IHD_SECURE_COOKIE=1`

3. Bring up the stack:

```bash
cd /path/to/repo/infra
docker compose -f docker-compose.prod.yml up -d --build
```

4. Verify the health endpoint:

```bash
./healthcheck.sh
```

### Cloudflare checklist

- In Cloudflare DNS, add `app.ithitdifferent.com` as an `A` record to your origin IP.
- Use `Proxied` if Cloudflare should terminate HTTPS.
- In Cloudflare SSL/TLS, set `Full (strict)` when origin TLS is valid.
- Enable `Always Use HTTPS` and `Automatic HTTPS Rewrites`.
- Confirm Cloudflare edge cert covers `app.ithitdifferent.com`.
- Keep only ports `80` and `443` open on the origin.

## Notes

- The app container binds to `IHD_HOST=0.0.0.0` and exposes only internal traffic to Caddy.
- Caddy uses the public hostname in `IHD_DOMAIN` and terminates HTTPS for the site.
- Do not expose port `8787` publicly.
- If using Cloudflare or another CDN, ensure the public DNS points to the proxy/edge service and the origin is reachable on ports `80`/`443`.
