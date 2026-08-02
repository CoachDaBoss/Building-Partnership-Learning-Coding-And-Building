import zipfile
from pathlib import Path
root = Path(__file__).resolve().parent
zip_path = root / 'deployment_bundle.zip'
files = [
    'README.md',
    '.env.example',
    'docs/DEPLOYMENT.md',
    'infra/README.md',
    'infra/bootstrap/README.md',
    'infra/bootstrap/linode-bootstrap.sh',
    'infra/bootstrap/ihd-docker-compose.service',
    'infra/docker-compose.prod.yml',
    'infra/docker-compose.caddy.example.yml',
    'infra/caddy/Caddyfile',
    'infra/start_prod.sh',
    'infra/healthcheck.sh',
    'deploy.sh',
]
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in files:
        p = root / f
        if p.exists():
            zf.write(p, arcname=f)
print(zip_path)
