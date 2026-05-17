# Deployment — relohelp2

CI builds Docker images, pushes to GHCR, and a deploy job SSHes to the production server, pulls the new images, and restarts the stack.

## Topology

```
Internet ─┬─ https://APP_DOMAIN ─→ host nginx ─→ frontend container (127.0.0.1:8080)
          │                                       └─ container nginx proxies /api,/auth,/ping to backend
          └─ https://API_DOMAIN ─→ host nginx ─→ backend container (127.0.0.1:8000)

docker compose (deploy/docker-compose.prod.yml) on the host:
  frontend  pulled from GHCR  → 127.0.0.1:8080
  backend   pulled from GHCR  → 127.0.0.1:8000
  mcp       pulled from GHCR  → internal only
  db        postgres:18-alpine → internal only (volume db_data)
```

SPA uses relative URLs in production (`frontend/src/api/client.ts`), so all SPA calls go through the app domain. The api domain exposes the same backend for external clients.

## GitHub configuration

Create an `production` environment (Settings → Environments → `production`) with:

**Variables** (Settings → Environments → `production` → Variables):
- `DEPLOY_SERVER` — ssh target, e.g. `user@host`
- `DEPLOY_DIR` — absolute path on server, e.g. `/opt/relohelp2`
- `APP_DOMAIN` — public app hostname
- `API_DOMAIN` — public api hostname

**Secrets**:
- `SSH_PRIVATE_KEY` — private key the GHA runner uses to ssh to `DEPLOY_SERVER`
- `SSH_KNOWN_HOSTS` — output of `ssh-keyscan <host>` for the same server
- `INTERNAL_API_TOKEN` — backend ↔ mcp shared secret
- `DB_USER`, `DB_PASSWORD`, `DB_NAME` — postgres creds

GHCR auth uses the workflow's `GITHUB_TOKEN`; no separate PAT needed as long as the package visibility lets the deploy user pull. The workflow logs the server into `ghcr.io` using the same token so private images can be pulled.

## CI workflow

`.github/workflows/deploy.yml` runs on push to `master` (or manual dispatch):

1. **`build-and-push`** — builds three images in parallel (`backend`, `mcp`, `frontend`) and pushes to `ghcr.io/<owner>/<repo>-<service>:<sha>` and `:latest`.
2. **`deploy`** — gated on the `production` environment; configures SSH, then runs `deploy/deploy.sh deploy` which syncs compose + nginx templates, writes `/opt/<dir>/.env` with secrets, logs the server into GHCR, `docker compose pull`, and `up -d`.

## Manual / one-time bootstrap

The server needs docker, nginx vhosts, and TLS certs once. Export the same env vars locally and run:

```bash
export SERVER=user@host \
       REMOTE_DIR=/opt/relohelp2 \
       APP_DOMAIN=app.relohelp.org \
       API_DOMAIN=api.relohelp.org \
       GHCR_NAMESPACE=<owner>/<repo> \
       IMAGE_TAG=latest \
       GHCR_USER=<gh-user> \
       GHCR_TOKEN=<ghcr-read-token> \
       INTERNAL_API_TOKEN=<token> \
       DB_USER=postgres DB_PASSWORD=<pw> DB_NAME=postgres \
       CERT_EMAIL=admin@example.com

bash deploy/deploy.sh bootstrap
```

This installs docker, renders nginx vhosts from `deploy/nginx/*.template.conf`, issues Let's Encrypt certs (`certbot --nginx --redirect`), writes `$REMOTE_DIR/.env`, and brings up the stack.

## Routine actions

- `bash deploy/deploy.sh deploy` — sync + pull + up
- `bash deploy/deploy.sh nginx`  — sync nginx templates + reload only

CI handles `deploy` automatically on every push to `master`.

## On the server

```bash
cd $REMOTE_DIR
docker compose -f deploy/docker-compose.prod.yml --env-file .env logs -f backend
docker compose -f deploy/docker-compose.prod.yml --env-file .env exec backend uv run alembic upgrade head
```

TLS renewal handled by certbot's systemd timer.
