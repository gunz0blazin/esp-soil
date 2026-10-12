#!/bin/sh
# One-time setup for the ESP-Soil Pi (Raspberry Pi OS 64-bit / Debian).
#
#   git clone https://github.com/gunz0blazin/esp-soil.git /tmp/esp-soil
#   sudo /tmp/esp-soil/deploy/bootstrap.sh
#
# Installs Docker, Ansible, git and rsync; creates /etc/esp-soil and asks for the
# secrets; installs the deploy command and the 5-minute timer; runs the first deploy.
# Safe to run again: it skips anything already done and never overwrites a secret.
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2; exit 1
fi

HERE=$(cd "$(dirname "$0")" && pwd)
SECRETS=/etc/esp-soil

echo "==> Packages"
apt-get update -q
apt-get install -y -q git rsync ansible-core ca-certificates curl

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Docker (official repository)"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
systemctl enable --now docker

echo "==> Secrets in $SECRETS"
install -d -m 0700 "$SECRETS"

ask_secret() {   # ask_secret <file> <prompt>
  if [ -s "$SECRETS/$1" ]; then
    echo "    $1 already set, keeping it"
    return
  fi
  printf '    %s: ' "$2"
  stty -echo 2>/dev/null || true
  read -r value
  stty echo 2>/dev/null || true
  echo
  [ -n "$value" ] || { echo "    empty, aborting" >&2; exit 1; }
  printf '%s' "$value" > "$SECRETS/$1"
  chmod 0600 "$SECRETS/$1"
}
ask_secret esp_web_password       "Stake web_password (same as in the ESPHome secrets.yaml)"
ask_secret grafana_admin_password "Grafana admin password (used the first time Grafana starts)"

if [ ! -e "$SECRETS/ntfy_url" ]; then
  printf '    ntfy topic URL for deploy notifications (Enter to skip): '
  read -r ntfy
  [ -n "$ntfy" ] && { printf '%s' "$ntfy" > "$SECRETS/ntfy_url"; chmod 0600 "$SECRETS/ntfy_url"; }
fi

if [ ! -e "$SECRETS/deploy.env" ]; then
  cat > "$SECRETS/deploy.env" <<'EOF'
# Which repo and branch this Pi deploys. main = only merged code.
REPO_URL=https://github.com/gunz0blazin/esp-soil.git
BRANCH=main
EOF
fi

echo "==> Deploy command and timer"
install -m 0755 "$HERE/esp-soil-deploy" /usr/local/bin/esp-soil-deploy
install -m 0644 "$HERE/systemd/esp-soil-deploy.service" /etc/systemd/system/
install -m 0644 "$HERE/systemd/esp-soil-deploy.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable esp-soil-deploy.timer

echo "==> First deploy (pulls images, can take a few minutes)"
/usr/local/bin/esp-soil-deploy --force
systemctl start esp-soil-deploy.timer

echo
echo "Done. Grafana: http://$(hostname -I | awk '{print $1}'):3000 (user admin)"
echo "The Pi now checks GitHub every 5 minutes. Logs: journalctl -u esp-soil-deploy"
