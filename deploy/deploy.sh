#!/usr/bin/env bash
# Deploy relohelp2 by pulling pre-built images from GHCR onto the configured server.
#
# Required env vars (set as GitHub Actions environment vars/secrets, or exported locally):
#   SERVER              ssh target, e.g. user@host
#   REMOTE_DIR          absolute path on server, e.g. /opt/relohelp2
#   APP_DOMAIN          public app domain (for nginx vhost)
#   API_DOMAIN          public api domain (for nginx vhost)
#   GHCR_NAMESPACE      owner/repo (case-insensitive; lowercased before use)
#   IMAGE_TAG           image tag to pull (commit sha in CI, "latest" otherwise)
#   GHCR_USER           ghcr login user
#   GHCR_TOKEN          ghcr token with read:packages
#   INTERNAL_API_TOKEN  shared secret backend <-> mcp
#   DB_USER DB_PASSWORD DB_NAME  postgres credentials
# Optional:
#   CERT_EMAIL          let's encrypt contact (only for `bootstrap`)
#   SSH_OPTS            extra ssh options (e.g. "-i /path/key")
#
# Usage:
#   bash deploy/deploy.sh deploy      # pull images + start stack
#   bash deploy/deploy.sh nginx       # sync nginx vhosts + reload
#   bash deploy/deploy.sh bootstrap   # install docker + nginx vhosts + certbot + first deploy
set -euo pipefail

ACTION="${1:-deploy}"

require_env() {
  local missing=()
  for v in "$@"; do
    if [ -z "${!v:-}" ]; then
      missing+=("$v")
    fi
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "missing required env vars: ${missing[*]}" >&2
    exit 2
  fi
}

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH_OPTS="${SSH_OPTS:-}"

ssh_run() { ssh $SSH_OPTS -o StrictHostKeyChecking=accept-new "$SERVER" "$@"; }
scp_to()  { scp $SSH_OPTS -o StrictHostKeyChecking=accept-new "$@"; }

ghcr_namespace_lower() {
  echo "$GHCR_NAMESPACE" | tr '[:upper:]' '[:lower:]'
}

sync_compose() {
  echo "==> sync docker-compose + nginx templates to $SERVER:$REMOTE_DIR"
  ssh_run "mkdir -p $REMOTE_DIR/deploy/nginx"
  scp_to "$REPO_ROOT/deploy/docker-compose.prod.yml" "$SERVER:$REMOTE_DIR/deploy/docker-compose.prod.yml"
  scp_to "$REPO_ROOT/deploy/nginx/app.template.conf" "$SERVER:$REMOTE_DIR/deploy/nginx/app.template.conf"
  scp_to "$REPO_ROOT/deploy/nginx/api.template.conf" "$SERVER:$REMOTE_DIR/deploy/nginx/api.template.conf"
  scp_to "$REPO_ROOT/deploy/install-server.sh"       "$SERVER:$REMOTE_DIR/deploy/install-server.sh"
}

write_remote_env() {
  echo "==> write $REMOTE_DIR/.env on server"
  local ns
  ns="$(ghcr_namespace_lower)"
  ssh_run "cat > $REMOTE_DIR/.env" <<EOF
GHCR_NAMESPACE=${ns}
IMAGE_TAG=${IMAGE_TAG}
INTERNAL_API_TOKEN=${INTERNAL_API_TOKEN}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_NAME=${DB_NAME}
EOF
}

render_nginx() {
  echo "==> render + install nginx vhosts ($APP_DOMAIN, $API_DOMAIN)"
  ssh_run "sed 's/__APP_DOMAIN__/${APP_DOMAIN}/g' $REMOTE_DIR/deploy/nginx/app.template.conf \
             > /etc/nginx/sites-available/${APP_DOMAIN}"
  ssh_run "sed 's/__API_DOMAIN__/${API_DOMAIN}/g' $REMOTE_DIR/deploy/nginx/api.template.conf \
             > /etc/nginx/sites-available/${API_DOMAIN}"
  ssh_run "ln -sfn /etc/nginx/sites-available/${APP_DOMAIN} /etc/nginx/sites-enabled/${APP_DOMAIN} && \
           ln -sfn /etc/nginx/sites-available/${API_DOMAIN} /etc/nginx/sites-enabled/${API_DOMAIN} && \
           nginx -t && systemctl reload nginx"
}

ghcr_login_remote() {
  echo "==> docker login ghcr.io on server"
  ssh_run "echo '${GHCR_TOKEN}' | docker login ghcr.io -u '${GHCR_USER}' --password-stdin"
}

compose_up() {
  echo "==> docker compose pull + up on $SERVER"
  ssh_run "cd $REMOTE_DIR && docker compose -f deploy/docker-compose.prod.yml --env-file .env pull && \
           docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --remove-orphans"
  ssh_run "cd $REMOTE_DIR && docker compose -f deploy/docker-compose.prod.yml ps"
}

issue_certs() {
  : "${CERT_EMAIL:?CERT_EMAIL required for bootstrap}"
  echo "==> issuing TLS certs via certbot"
  ssh_run "certbot --nginx --non-interactive --agree-tos -m '${CERT_EMAIL}' \
    -d '${APP_DOMAIN}' -d '${API_DOMAIN}' --redirect"
}

case "$ACTION" in
  bootstrap)
    require_env SERVER REMOTE_DIR APP_DOMAIN API_DOMAIN \
                GHCR_NAMESPACE IMAGE_TAG GHCR_USER GHCR_TOKEN \
                INTERNAL_API_TOKEN DB_USER DB_PASSWORD DB_NAME CERT_EMAIL
    sync_compose
    ssh_run "bash $REMOTE_DIR/deploy/install-server.sh"
    render_nginx
    issue_certs
    write_remote_env
    ghcr_login_remote
    compose_up
    ;;
  nginx)
    require_env SERVER REMOTE_DIR APP_DOMAIN API_DOMAIN
    sync_compose
    render_nginx
    ;;
  deploy|"")
    require_env SERVER REMOTE_DIR \
                GHCR_NAMESPACE IMAGE_TAG GHCR_USER GHCR_TOKEN \
                INTERNAL_API_TOKEN DB_USER DB_PASSWORD DB_NAME
    sync_compose
    write_remote_env
    ghcr_login_remote
    compose_up
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    exit 2
    ;;
esac

echo "==> done"
