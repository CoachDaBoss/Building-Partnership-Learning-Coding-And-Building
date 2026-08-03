# Render + Neon setup for IT HIT DIFFERENT

This build supports PostgreSQL whenever `DATABASE_URL` is set. Without it, it falls back to local SQLite for development.

## Render settings

- Runtime: Python 3
- Build Command: `pip install -r requirements.txt && python -m compileall server.py`
- Start Command: `IHD_HOST=0.0.0.0 IHD_PORT=$PORT python server.py`
- Health Check Path: `/api/health`

## Required Render environment variables

- `DATABASE_URL` = your Neon PostgreSQL connection string
- `IHD_MASTER_NAME` = master owner display name
- `IHD_MASTER_EMAIL` = master owner email
- `IHD_MASTER_PASSWORD` = strong private master password
- `IHD_SECURE_COOKIE` = `1`
- `IHD_DOMAIN` = `ithitdifferent.onrender.com`

Do not commit `DATABASE_URL`, `.env`, passwords, API keys, or local database files to GitHub.

## What changed

- Public `Create Account` flow at the login gate.
- `/api/register` endpoint.
- New registrations are `creator`, active, and unverified.
- Admin/master verification and role controls remain unchanged.
- PostgreSQL/Neon persistence for users, sessions, projects, rooms, releases, and other database records.
- SQLite remains available for local development only.

## Important

Uploaded media is still stored in `data/uploads` on the Render filesystem. On Render Free, that file storage is ephemeral. Account/database persistence is fixed by Neon, but permanent media storage should later be moved to object storage (for example Cloudflare R2, S3, or another compatible service).
