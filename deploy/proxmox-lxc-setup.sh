#!/bin/sh
# Prepare a Proxmox LXC container to run ESP-Soil (test setups; a real Pi doesn't need this).
# Run this ON THE PROXMOX HOST, not inside the container:
#
#   curl -fsSL https://raw.githubusercontent.com/gunz0blazin/esp-soil/main/deploy/proxmox-lxc-setup.sh | sh -s -- <CTID>
#
# (Use .../esp-soil/testing/deploy/... while this is only on the testing branch.)
# Find the container ID with `pct list`.
#
# It makes sure the container has:
#   - /dev/net/tun passed through, which Tailscale needs
#   - the nesting feature (and keyctl if unprivileged), which Docker needs
# Existing settings are kept; nothing is added twice. The container restarts only
# if something changed. Then run deploy/bootstrap.sh inside it again.
set -eu

CT=${1:-}
if [ -z "$CT" ]; then
  echo "Usage: $0 <container-id>    (see: pct list)" >&2; exit 1
fi
if ! command -v pct >/dev/null 2>&1; then
  echo "pct not found: run this on the Proxmox host, not inside the container." >&2; exit 1
fi
CONF=/etc/pve/lxc/$CT.conf
if [ ! -f "$CONF" ]; then
  echo "No container $CT ($CONF not found). Check the ID with: pct list" >&2; exit 1
fi

# Only the container's current settings, not the [snapshot] sections below them.
current() { awk '/^\[/ { exit } { print }' "$CONF"; }

CHANGED=no
echo "==> Container $CT ($(current | sed -n 's/^hostname: //p'))"

# ---- TUN device for Tailscale ----
if current | grep -q '^lxc.mount.entry: /dev/net/tun'; then
  echo "    TUN passthrough: already set"
else
  # Raw lxc.* lines must sit above any [snapshot] sections, so insert them
  # before the first one (or append if there are none).
  tmp=$(mktemp)
  awk '
    !done && /^\[/ {
      print "lxc.cgroup2.devices.allow: c 10:200 rwm"
      print "lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file"
      done = 1
    }
    { print }
    END {
      if (!done) {
        print "lxc.cgroup2.devices.allow: c 10:200 rwm"
        print "lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file"
      }
    }' "$CONF" > "$tmp"
  cat "$tmp" > "$CONF"
  rm -f "$tmp"
  echo "    TUN passthrough: added"
  CHANGED=yes
fi

# ---- nesting (and keyctl for unprivileged containers) for Docker ----
features=$(current | sed -n 's/^features: //p' | head -n 1)
want="nesting=1"
if current | grep -q '^unprivileged: 1'; then
  want="$want keyctl=1"
fi
new=$features
for f in $want; do
  key=${f%%=*}
  case ",$new," in
    *",$f,"*) ;;                                              # already set
    *",$key="*) new=$(printf '%s' "$new" | sed "s/\(^\|,\)$key=[^,]*/\1$f/") ;;   # set to 0, flip it
    *) new=${new:+$new,}$f ;;
  esac
done
if [ "$new" = "$features" ]; then
  echo "    Features: already set ($features)"
else
  pct set "$CT" --features "$new"
  echo "    Features: ${features:-none} -> $new"
  CHANGED=yes
fi

if [ "$CHANGED" = yes ]; then
  if pct status "$CT" | grep -q running; then
    echo "==> Restarting container $CT"
    pct reboot "$CT"
  fi
  echo "Done. Inside the container, run the bootstrap again; it continues where it stopped."
else
  echo "Nothing to change."
fi
