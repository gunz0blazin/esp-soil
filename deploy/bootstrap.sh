#!/bin/sh
# One-time setup for the ESP-Soil Pi (Raspberry Pi OS 64-bit / Debian).
#
#   git clone https://github.com/gunz0blazin/esp-soil.git /tmp/esp-soil
#   sudo /tmp/esp-soil/deploy/bootstrap.sh
#
# Installs Docker, Ansible, git and rsync; creates /etc/esp-soil and asks for the
# secrets; installs the deploy command and the 5-minute timer; runs the first deploy;
# then sets the Pi up as a Tailscale subnet router for the site VLAN (deploy/TAILSCALE.md).
# Safe to run again: it skips anything already done and never overwrites a secret.
#
# Options:
#   --no-tailscale           skip the Tailscale step
# Environment (all optional):
#   BRANCH=testing           branch this Pi deploys; default: the branch this copy was
#                            cloned from (clone -b testing to test the pipeline itself)
#   TS_ROUTES=10.42.0.0/24   subnet to share; default: the subnet of the Pi's main interface
#   TS_HOSTNAME=esp-soil-pi  the Pi's name on the tailnet; default: esp-soil-pi
#   TS_AUTHKEY=tskey-...     log in with an auth key instead of opening the printed link
set -eu

SETUP_TAILSCALE=yes
for arg in "$@"; do
  case "$arg" in
    --no-tailscale) SETUP_TAILSCALE=no ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2; exit 1
fi

HERE=$(cd "$(dirname "$0")" && pwd)
SECRETS=/etc/esp-soil

# Deploy the branch this copy was cloned from, unless BRANCH says otherwise.
# safe.directory: the clone belongs to your user, but this runs as root.
if [ -z "${BRANCH:-}" ]; then
  BRANCH=$(git -c safe.directory='*' -C "$HERE" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  case "$BRANCH" in ""|HEAD) BRANCH=main ;; esac
fi
echo "==> This Pi will deploy branch: $BRANCH"

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
  cat > "$SECRETS/deploy.env" <<EOF
# Which repo and branch this Pi deploys. main = only merged code.
REPO_URL=https://github.com/gunz0blazin/esp-soil.git
BRANCH=$BRANCH
EOF
else
  current=$(sed -n 's/^BRANCH=//p' "$SECRETS/deploy.env")
  if [ "$current" != "$BRANCH" ]; then
    echo "    deploy.env: switching BRANCH from ${current:-unset} to $BRANCH"
    if grep -q '^BRANCH=' "$SECRETS/deploy.env"; then
      sed -i "s/^BRANCH=.*/BRANCH=$BRANCH/" "$SECRETS/deploy.env"
    else
      echo "BRANCH=$BRANCH" >> "$SECRETS/deploy.env"
    fi
  fi
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

TS_DONE=no
if [ "$SETUP_TAILSCALE" = yes ]; then
  echo "==> Tailscale (subnet router for the site VLAN)"
  if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
  fi

  # Let the Pi forward traffic between the tailnet and the VLAN.
  printf 'net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n' > /etc/sysctl.d/99-tailscale.conf
  sysctl -q -p /etc/sysctl.d/99-tailscale.conf

  # The subnet to share: the one the Pi's main interface is on, unless TS_ROUTES says otherwise.
  if [ -z "${TS_ROUTES:-}" ]; then
    iface=$(ip route show default | awk '{print $5; exit}')
    cidr=$(ip -4 -o addr show dev "$iface" scope global | awk '{print $4; exit}')
    TS_ROUTES=$(python3 -c 'import ipaddress, sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$cidr")
    echo "    Pi is $cidr on $iface, sharing $TS_ROUTES (set TS_ROUTES to change)"
  fi
  TS_HOSTNAME=${TS_HOSTNAME:-esp-soil-pi}

  state=$(tailscale status --json 2>/dev/null \
    | python3 -c 'import json, sys; print(json.load(sys.stdin).get("BackendState", ""))' 2>/dev/null || true)
  if [ "$state" = Running ]; then
    echo "    already logged in; making sure the route and name are set"
    tailscale set --advertise-routes="$TS_ROUTES" --hostname="$TS_HOSTNAME"
  elif [ -n "${TS_AUTHKEY:-}" ]; then
    tailscale up --auth-key="$TS_AUTHKEY" --advertise-routes="$TS_ROUTES" --hostname="$TS_HOSTNAME"
  else
    echo "    Open the link below and log in to your Tailscale account:"
    tailscale up --advertise-routes="$TS_ROUTES" --hostname="$TS_HOSTNAME"
  fi
  TS_DONE=yes
fi

echo
echo "Done. Grafana: http://$(hostname -I | awk '{print $1}'):3000 (user admin)"
echo "The Pi now checks GitHub every 5 minutes. Logs: journalctl -u esp-soil-deploy"
if [ "$TS_DONE" = yes ]; then
  echo
  echo "Two clicks left in the Tailscale admin console, Machines page (deploy/TAILSCALE.md):"
  echo "  1. $TS_HOSTNAME: Subnets -> Edit -> approve $TS_ROUTES"
  echo "  2. $TS_HOSTNAME: ... menu -> Disable key expiry  (or the site drops off in a few months)"
  echo "Then Grafana is at http://$TS_HOSTNAME:3000 from anywhere on your tailnet."
fi
