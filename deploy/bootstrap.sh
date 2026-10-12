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
#   PI_STATIC_IP=10.42.0.10/24  give the Pi a static address (NetworkManager). Saved now,
#                            used from the next boot, so it's safe to set at home before
#                            taking the Pi to the site. PI_GATEWAY / PI_DNS default to the
#                            subnet's .1. Also sets the Tailscale subnet if TS_ROUTES isn't set.
#   TS_ROUTES=10.42.0.0/24   subnet to share; default: PI_STATIC_IP's subnet, else the subnet
#                            of the Pi's main interface
#   TS_HOSTNAME=esp-soil-pi  the Pi's name on the tailnet; default: esp-soil-pi, or the
#                            machine's own hostname in a container (so a test box never
#                            takes the real Pi's name)
#   TS_AUTHKEY=tskey-...     log in with an auth key instead of opening the printed link
#
# Detects where it's running (Raspberry Pi, container, VM) and adjusts: in a container
# it checks that the container has the TUN device and can run Docker.
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

# ---- where are we running? ----
IN_CONTAINER=no
VIRT=$(systemd-detect-virt 2>/dev/null || true)          # none, lxc, kvm, ...
if grep -qa 'Raspberry Pi' /proc/device-tree/model 2>/dev/null; then
  PLATFORM="Raspberry Pi ($(tr -d '\0' < /proc/device-tree/model))"
elif systemd-detect-virt --container >/dev/null 2>&1; then
  IN_CONTAINER=yes
  PLATFORM="container ($VIRT)"
elif [ -n "$VIRT" ] && [ "$VIRT" != none ]; then
  PLATFORM="virtual machine ($VIRT)"
else
  PLATFORM="physical machine"
fi
echo "==> Running on: $PLATFORM"
if [ "$IN_CONTAINER" = yes ]; then
  echo "    Container mode: Tailscale uses this machine's hostname, and the script checks"
  echo "    that the container has what it needs (TUN device, Docker)."
fi

# Deploy the branch this copy was cloned from, unless BRANCH says otherwise.
# safe.directory: the clone belongs to your user, but this runs as root.
if [ -z "${BRANCH:-}" ]; then
  BRANCH=$(git -c safe.directory='*' -C "$HERE" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
  case "$BRANCH" in ""|HEAD) BRANCH=main ;; esac
fi
echo "==> This Pi will deploy branch: $BRANCH"

echo "==> Packages"
apt-get update
# procps (sysctl) and iproute2 (ip) are missing from minimal installs and containers
apt-get install -y git rsync ansible-core ca-certificates curl procps iproute2 python3

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Docker (official repository)"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
systemctl enable --now docker
if ! docker info >/dev/null 2>&1; then
  echo "    Docker isn't running. See why: journalctl -u docker -n 30 --no-pager" >&2
  if [ "$IN_CONTAINER" = yes ]; then
    echo "    Containers need nesting enabled on their host to run Docker. Enable it," >&2
    echo "    restart the container, then run this script again." >&2
  fi
  exit 1
fi

echo "==> Secrets in $SECRETS"
install -d -m 0700 "$SECRETS"

ask_secret() {   # ask_secret <file> <prompt>
  if [ -s "$SECRETS/$1" ]; then
    echo "    $1 already set, keeping it"
    return
  fi
  # Typed in the clear on purpose, so you can see what you entered.
  printf '    %s: ' "$2"
  read -r value
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

# ---- which stakes this box watches ----
# A test box (cloned from a branch other than main) can watch its own probe instead
# of the site stakes: a list in /etc/esp-soil/targets/ replaces the repo's list on
# this box only. Production (main) uses the repo's list.
LOCAL_TARGETS="$SECRETS/targets"
has_local_targets() { ls "$LOCAL_TARGETS"/*.yml >/dev/null 2>&1; }
if [ "$BRANCH" != main ]; then
  echo "==> Stakes for this test box"
  if has_local_targets; then
    echo "    already using this box's own list: $(cd "$LOCAL_TARGETS" && ls -- *.yml | tr '\n' ' ')"
  else
    if [ -z "${TEST_PROBE_IP:-}" ]; then
      printf "    Test probe IP (Enter to skip and watch the repo's site stakes instead): "
      read -r TEST_PROBE_IP
    fi
    if [ -n "$TEST_PROBE_IP" ]; then
      case "$TEST_PROBE_IP" in *:*) target="$TEST_PROBE_IP" ;; *) target="$TEST_PROBE_IP:80" ;; esac
      install -d -m 0755 "$LOCAL_TARGETS"
      {
        echo "# This box's own list of stakes. It replaces the repo's list on this box only."
        echo "# Add more entries the same way; Prometheus picks up changes within a minute."
        echo "- targets: [\"$target\"]"
        echo "  labels: {board: test-probe}"
      } > "$LOCAL_TARGETS/test-probe.yml"
      chmod 0644 "$LOCAL_TARGETS/test-probe.yml"
      echo "    wrote $LOCAL_TARGETS/test-probe.yml ($target)"
    fi
  fi
elif has_local_targets; then
  echo "==> NOTE: this box deploys main but has its own list of stakes in $LOCAL_TARGETS,"
  echo "    so it ignores the repo's list. Remove those files on a production Pi."
fi

echo "==> Deploy command and timer"
install -m 0755 "$HERE/esp-soil-deploy" /usr/local/bin/esp-soil-deploy
install -m 0644 "$HERE/systemd/esp-soil-deploy.service" /etc/systemd/system/
install -m 0644 "$HERE/systemd/esp-soil-deploy.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable esp-soil-deploy.timer

# Pull the images here, outside Ansible, so Docker's progress streams live.
# (Ansible only prints a task's output once the task has finished.)
echo "==> Pulling Prometheus and Grafana images"
GRAFANA_ADMIN_PASSWORD=pull-only docker compose --progress plain \
  -f "$HERE/../dashboard/docker-compose.yml" pull

echo "==> First deploy"
/usr/local/bin/esp-soil-deploy --force
systemctl start esp-soil-deploy.timer

# ---- static address for the Pi (optional) ----
# Saved in NetworkManager but not applied now: if this runs at home, switching to the
# site's address would cut the connection. It takes effect on the next boot.
STATIC_PENDING=no
if [ -n "${PI_STATIC_IP:-}" ]; then
  echo "==> Static address: $PI_STATIC_IP"
  case "$PI_STATIC_IP" in */*) ;; *) echo "    PI_STATIC_IP needs a prefix, e.g. 10.42.0.10/24" >&2; exit 1 ;; esac
  STATIC_NET=$(python3 -c 'import ipaddress, sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$PI_STATIC_IP")
  PI_GATEWAY=${PI_GATEWAY:-$(python3 -c 'import ipaddress, sys; print(next(ipaddress.ip_network(sys.argv[1]).hosts()))' "$STATIC_NET")}
  PI_DNS=${PI_DNS:-$PI_GATEWAY}
  [ -z "${TS_ROUTES:-}" ] && TS_ROUTES=$STATIC_NET
  if [ "$IN_CONTAINER" = yes ]; then
    echo "    skipped: a container's address is set on its host"
  elif ! command -v nmcli >/dev/null 2>&1; then
    echo "    skipped: NetworkManager (nmcli) isn't installed; set the address by hand" >&2
  else
    iface=$(ip route show default | awk '{print $5; exit}')
    con=$(nmcli -t -f NAME,DEVICE connection show --active | awk -F: -v d="$iface" '$2 == d {print $1; exit}')
    if [ -z "$con" ]; then
      echo "    skipped: no active NetworkManager connection on $iface" >&2
    else
      nmcli connection modify "$con" ipv4.method manual ipv4.addresses "$PI_STATIC_IP" \
        ipv4.gateway "$PI_GATEWAY" ipv4.dns "$PI_DNS"
      echo "    saved on '$con' ($iface): $PI_STATIC_IP, gateway $PI_GATEWAY, DNS $PI_DNS"
      echo "    It takes effect on the next boot. Until then the Pi keeps its current address."
      STATIC_PENDING=yes
    fi
  fi
fi

TS_DONE=no
if [ "$SETUP_TAILSCALE" = yes ] && [ ! -c /dev/net/tun ]; then
  # Tailscale needs the TUN device. A Raspberry Pi always has it; a container
  # doesn't until its host passes it through.
  echo "==> Tailscale: SKIPPED, /dev/net/tun is missing"
  if [ "$IN_CONTAINER" = yes ]; then
    echo "    Containers don't get the TUN device by default, and a container can't grant it"
    echo "    to itself: pass /dev/net/tun through from the container's host, restart the"
    echo "    container, then run this script again here; it skips what's already done."
  else
    echo "    Load the TUN module (modprobe tun) and run this script again."
  fi
  SETUP_TAILSCALE=no
  TS_DONE=skipped
fi
if [ "$SETUP_TAILSCALE" = yes ]; then
  echo "==> Tailscale (subnet router for the site VLAN)"
  if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
  fi
  systemctl enable --now tailscaled
  ready=no
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if tailscale status --json >/dev/null 2>&1 || tailscale status 2>&1 | grep -qi 'logged out'; then
      ready=yes; break
    fi
    sleep 1
  done
  if [ "$ready" = no ]; then
    echo "    tailscaled isn't running. See why: journalctl -u tailscaled -n 30 --no-pager" >&2
    exit 1
  fi

  # Let the Pi forward traffic between the tailnet and the VLAN.
  printf 'net.ipv4.ip_forward = 1\nnet.ipv6.conf.all.forwarding = 1\n' > /etc/sysctl.d/99-tailscale.conf
  if [ "$IN_CONTAINER" = yes ]; then
    # Some container setups don't allow changing these; only IPv4 forwarding matters here.
    sysctl -p /etc/sysctl.d/99-tailscale.conf || true
    if [ "$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null)" != 1 ]; then
      echo "    WARNING: IPv4 forwarding is off and the container can't turn it on, so other" >&2
      echo "    tailnet devices won't reach the subnet through it. Enable it on the host." >&2
    fi
  else
    sysctl -p /etc/sysctl.d/99-tailscale.conf
  fi

  # The subnet to share: the one the Pi's main interface is on, unless TS_ROUTES says otherwise.
  if [ -z "${TS_ROUTES:-}" ]; then
    iface=$(ip route show default | awk '{print $5; exit}')
    cidr=$(ip -4 -o addr show dev "$iface" scope global | awk '{print $4; exit}')
    TS_ROUTES=$(python3 -c 'import ipaddress, sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$cidr")
    echo "    This machine is $cidr on $iface, sharing $TS_ROUTES (set TS_ROUTES to change)"
  fi
  if [ "$IN_CONTAINER" = yes ]; then
    TS_HOSTNAME=${TS_HOSTNAME:-$(hostname)}     # a test box shouldn't take the real Pi's name
  else
    TS_HOSTNAME=${TS_HOSTNAME:-esp-soil-pi}
  fi
  echo "    Tailnet name: $TS_HOSTNAME"

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
echo "==> Checking everything is running"
wait_for() {   # wait_for <url>: up to 60 s
  i=0
  while [ "$i" -lt 30 ]; do
    curl -fsS -o /dev/null "$1" 2>/dev/null && return 0
    i=$((i + 1)); sleep 2
  done
  return 1
}
PROM_STATE=running; wait_for http://127.0.0.1:9090/-/ready    || PROM_STATE="NOT RESPONDING"
GRAF_STATE=running; wait_for http://127.0.0.1:3000/api/health || GRAF_STATE="NOT RESPONDING"

GRAF_PW=$(cat "$SECRETS/grafana_admin_password")
WEB_PW=$(cat "$SECRETS/esp_web_password")
WEB_USER=$(sed -n 's/^ *username: *//p' /opt/esp-soil/dashboard/prometheus/prometheus.yml 2>/dev/null | head -n 1)
WEB_USER=${WEB_USER:-esp}
if [ "$GRAF_STATE" = running ]; then
  if curl -fsS -o /dev/null -u "admin:$GRAF_PW" http://127.0.0.1:3000/api/user 2>/dev/null; then
    GRAF_LOGIN="login checked, works"
  else
    GRAF_LOGIN="LOGIN FAILED: the password was probably changed in Grafana since its first start"
  fi
else
  GRAF_LOGIN="not checked"
fi
LAN_IP=$(hostname -I | awk '{print $1}')
TS_IP=""
[ "$TS_DONE" = yes ] && TS_IP=$(tailscale ip -4 2>/dev/null | head -n 1 || true)

echo
echo "================================================================"
echo " ESP-Soil on $(hostname)  ($PLATFORM)"
echo " Deploys branch '$BRANCH' every 5 minutes  (journalctl -u esp-soil-deploy)"
if has_local_targets; then
  echo " Stakes: this box's own list ($LOCAL_TARGETS)"
else
  echo " Stakes: the repo's list (dashboard/prometheus/targets)"
fi
echo "----------------------------------------------------------------"
echo " Grafana     [$GRAF_STATE]"
echo "   http://$LAN_IP:3000"
[ -n "$TS_IP" ] && echo "   http://$TS_HOSTNAME:3000  /  http://$TS_IP:3000   (tailnet)"
echo "   user: admin    password: $GRAF_PW"
echo "   ($GRAF_LOGIN)"
echo
echo " Prometheus  [$PROM_STATE]"
echo "   http://$LAN_IP:9090"
[ -n "$TS_IP" ] && echo "   http://$TS_HOSTNAME:9090  /  http://$TS_IP:9090   (tailnet)"
echo "   no login: keep it on your own network / tailnet"
echo
echo " Stakes (web page + /metrics, used by Prometheus)"
echo "   user: $WEB_USER    password: $WEB_PW"
echo "================================================================"
if [ "$STATIC_PENDING" = yes ]; then
  echo " After the next boot this machine is ${PI_STATIC_IP%/*} (static):"
  echo "   Grafana http://${PI_STATIC_IP%/*}:3000   Prometheus http://${PI_STATIC_IP%/*}:9090"
  echo "----------------------------------------------------------------"
fi
echo " Passwords are stored in $SECRETS/ (root only)."

if [ "$PROM_STATE" != running ] || [ "$GRAF_STATE" != running ]; then
  echo
  echo "Something isn't running. Check: cd /opt/esp-soil/dashboard && docker compose -p esp-soil ps" >&2
  exit 1
fi
if [ "$TS_DONE" = skipped ]; then
  echo
  echo "Tailscale was skipped: /dev/net/tun is missing (see the message above)."
fi
if [ "$TS_DONE" = yes ]; then
  echo
  echo "Two clicks left in the Tailscale admin console, Machines page (deploy/TAILSCALE.md):"
  echo "  1. $TS_HOSTNAME: Subnets -> Edit -> approve $TS_ROUTES"
  echo "  2. $TS_HOSTNAME: ... menu -> Disable key expiry  (or the site drops off in a few months)"
  echo "Then Grafana is at http://$TS_HOSTNAME:3000 from anywhere on your tailnet."
fi
