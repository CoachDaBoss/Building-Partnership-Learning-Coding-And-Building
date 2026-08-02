# Deployment Notes

## Private VPS / dedicated server

Use a Linux VPS or dedicated host and bind the app to localhost behind an HTTPS reverse proxy.

```bash
export IHD_HOST=127.0.0.1
export IHD_PORT=8787
export IHD_SECURE_COOKIE=1
python3 server.py
```

Terminate HTTPS with Caddy/Nginx or another hardened reverse proxy. For a complete containerized example, use `infra/docker-compose.prod.yml` together with the included `infra/Dockerfile` and Caddyfile.

Before running, copy `.env.example` to `.env` at the repository root and set `IHD_DOMAIN`, `IHD_MASTER_EMAIL`, `IHD_MASTER_PASSWORD`, and other required secrets. Make sure the app binds internally on `IHD_HOST=0.0.0.0` so Caddy can proxy to it from the Docker network.

```bash
cp .env.example .env
docker compose -f infra/docker-compose.prod.yml up -d --build
```

If you want a minimal local example for testing, `infra/docker-compose.caddy.example.yml` can also be used.

Then point your public domain to the host and do not expose the raw development HTTP port directly to the public internet.

If your browser shows `ERR_CERT_COMMON_NAME_INVALID` or a certificate from `*.sucuri.net`, the public endpoint is not serving a valid certificate for the domain you set in `IHD_DOMAIN`.

- Configure your proxy/CDN to serve TLS for the domain set in `IHD_DOMAIN`.
- Do not use a generic proxy hostname such as `*.sucuri.net` as the public URL.
- If using Sucuri, add the domain in `IHD_DOMAIN` as a protected site and enable SSL for that domain.
- If using Cloudflare, use the shared edge certificate or upload a custom cert and enable `Full (strict)` if possible.

### Cloudflare checklist

- Add `app.ithitdifferent.com` as an `A` record in Cloudflare DNS.
- Point the record to your origin server IP.
- Enable the orange cloud only if Cloudflare should proxy HTTPS.
- Set SSL/TLS mode to `Full (strict)` when origin TLS is valid.
- Enable `Always Use HTTPS` and `Automatic HTTPS Rewrites`.
- Confirm the Cloudflare edge certificate covers `app.ithitdifferent.com`.
- Allow only ports `80` and `443` to the origin.

### Proxy/TLS checklist

1. Confirm DNS points to the proxy/CDN service for the domain set in `IHD_DOMAIN`.
2. Confirm the proxy is configured for your exact hostname (the value of `IHD_DOMAIN`), not a vendor test domain.
3. Confirm the proxy is issuing or proxying a certificate for the domain in `IHD_DOMAIN`.
4. Confirm the origin server is not exposed directly on port `8787`.
5. If using origin TLS, confirm the origin certificate is valid or the proxy is in `Full (strict)` mode.

## Live sessions

The browser client reads ICE server configuration from the backend. By default the list is empty, which is suitable for direct/LAN testing but not reliable across every internet/NAT combination.

For your own coturn server (use `IHD_DOMAIN` to build the TURN hostname):

```bash
export IHD_STUN_URL="stun:turn.${IHD_DOMAIN}:3478"
export IHD_TURN_URL="turn:${IHD_DOMAIN}:3478"
export IHD_TURN_USERNAME="ihd-user"
export IHD_TURN_PASSWORD="CHANGE_ME"
```

For large multi-user sessions, use the included LiveKit production direction rather than browser mesh video.

## Backups

Run:

```bash
python3 scripts/backup.py
```

This creates a ZIP of the local `data/` directory. In production, back up PostgreSQL/object storage independently and encrypt offsite backups.
