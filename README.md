# IT HIT DIFFERENT LLC — Creator Network v1

A self-hosted, working MVP for a private music-creator platform.

## What is working now

- Private login gate backed by server sessions
- One protected `SUPER_ADMIN` master owner created on first boot
- PBKDF2 password hashing, HttpOnly SameSite session cookie, CSRF tokens and audit events
- Master user creation, verification, producer/artist roles and suspensions
- Browser microphone recording with gain, high-pass, presence and delay controls
- Private audio-take uploads and persistent studio project records
- 16-step browser beat builder
- Verified-producer beat upload/library with licensing terms, BPM and key
- Safe unlimited plugin-preset registry using approved WebAudio processor types
- Verified-user release vault with separate composition/master split ledgers
- Rights attestation and public IHD release share pages
- Live collaboration rooms with room codes, answer/decline invitations, group chat, camera/microphone, screen sharing and WebRTC signaling through this server
- Persistent EPK profile
- Royalties/business education center
- Master audit log

## Run it

Requirements: Python 3.11+ (no third-party Python packages required).

### Windows PowerShell

```powershell
$env:IHD_MASTER_EMAIL="you@example.com"
$env:IHD_MASTER_PASSWORD="Use-A-Long-Unique-Password"
$env:IHD_MASTER_NAME="CoachDaBoss"
python server.py
```

### Linux / macOS

```bash
export IHD_MASTER_EMAIL="you@example.com"
export IHD_MASTER_PASSWORD="Use-A-Long-Unique-Password"
export IHD_MASTER_NAME="CoachDaBoss"
python3 server.py
```

Open `http://127.0.0.1:8787`.

If you do **not** set `IHD_MASTER_PASSWORD`, the server generates a master password and prints it once in the terminal on first boot.

The database is `data/ihd.sqlite3`; uploaded private files are under `data/uploads/`.

## LAN testing

```bash
IHD_HOST=0.0.0.0 python3 server.py
```

Then open `http://<server-lan-ip>:8787` from another device on the same network. Note: modern browsers often require HTTPS for camera/microphone outside localhost.

## Container deployment

A Dockerfile and HTTPS reverse-proxy example are included under `infra/`.

- `infra/Dockerfile`
- `infra/docker-compose.prod.yml`
- `infra/caddy/Caddyfile`

Before starting the stack, copy `.env.example` to `.env` at the repository root and edit it with your domain, master credentials, and any TURN/STUN settings.

```bash
cp .env.example .env
# edit .env to set IHD_DOMAIN, IHD_MASTER_EMAIL, IHD_MASTER_PASSWORD, and secret values

docker compose -f infra/docker-compose.prod.yml up -d --build
```

Set `IHD_SECURE_COOKIE=1` before public launch and do not expose port `8787` directly to the internet.

### Deployer script

After creating and editing `.env`, use the repo root deployer:

```bash
./deploy.sh
```

For remote deploys via SSH:

```bash
./deploy.sh --host root@1.2.3.4 --dir /opt/ihd --healthcheck
```

If you see a browser TLS error for the domain in `IHD_DOMAIN` and the certificate is from `*.sucuri.net`, stop using the generic proxy endpoint. Make sure the domain set in `IHD_DOMAIN` is configured in the security/CDN service and that it is serving a certificate matching that hostname.

### Cloudflare checklist

- `app.ithitdifferent.com` must be added as a DNS record in your Cloudflare zone.
- Use an `A` record pointing to your origin IP.
- Set `Proxy status` to `Proxied` if Cloudflare should terminate HTTPS.
- In Cloudflare SSL/TLS, use `Full (strict)` when origin TLS is valid.
- Enable `Always Use HTTPS` and `Automatic HTTPS Rewrites`.
- Confirm Cloudflare edge cert covers `app.ithitdifferent.com`.
- Do not expose port `8787` publicly; only ports `80` and `443` should be open.

### TLS troubleshooting checklist

- Confirm the domain in `IHD_DOMAIN` is added and enabled in the proxy/CDN.
- Confirm the public hostname is the value of `IHD_DOMAIN`, not a vendor hostname like `*.sucuri.net`.
- Confirm the proxy is serving a certificate for the domain in `IHD_DOMAIN`.
- Confirm the proxy is forwarding traffic to your origin without exposing port `8787` publicly.
- If using Cloudflare or Sucuri, prefer `Full (strict)` when origin TLS is available.

## Production requirements before public launch

This v1 is a strong functional MVP, not a claim that a single Python process is the final worldwide production architecture. Before a public launch:

1. Put the app behind HTTPS (Caddy/Nginx/Cloudflare Tunnel or a hardened reverse proxy).
2. Set `IHD_SECURE_COOKIE=1` after HTTPS is active.
3. Move relational data to PostgreSQL and large media to private S3/MinIO storage with signed URLs.
4. Add MFA/passkeys, recovery codes, rate limiting, email verification and device/session management.
5. Run malware/file-signature validation on uploads and create transcoded preview files.
6. Add a private TURN server for reliable WebRTC across NAT/firewalls; for large group sessions, move media to self-hosted LiveKit/SFU.
7. Have licensed counsel review privacy, Terms, DMCA/copyright process, minors policy and jurisdiction-specific business guidance.
8. Use supported OAuth/platform APIs for direct social publishing. The built-in share layer should remain the universal fallback.
9. Add backups, monitoring, alerting, log retention and a disaster-recovery process.
10. Never host arbitrary uploaded native VST/AU binaries inside the web server. Native plugins belong in a signed desktop companion/sandbox.

## Primary owner model

The first master account has role `super_admin`. API rules prevent delegated admins from demoting, suspending or editing that owner. Only the master owner can grant admin access.

There is intentionally **no hidden backdoor**. Owner control is implemented as explicit, audited authority.
