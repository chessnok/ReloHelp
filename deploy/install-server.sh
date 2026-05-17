#!/usr/bin/env bash
# One-time server bootstrap: installs docker engine + compose plugin on Ubuntu 24.04.
# Run on server as root: bash /opt/relohelp2/deploy/install-server.sh
set -euo pipefail

if command -v docker >/dev/null 2>&1; then
  echo "docker already installed: $(docker --version)"
else
  echo "Installing docker engine..."
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

docker --version
docker compose version
