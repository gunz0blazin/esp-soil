"""Check the stake addresses agree everywhere.

Each stake's IP lives in two places in the repo:
  - firmware/stakes/soil-stake-N.yaml   stake_ip (the stake sets this on itself)
  - dashboard/prometheus/targets/*.yml  where Prometheus scrapes it
This fails if they disagree, if two stakes share an IP, or if an IP isn't inside
the network given by the firmware's gateway/subnet.
It also checks the Pi's planned address in deploy/site.env: on the stakes'
network, same gateway, and not any stake's address.
"""
import glob
import ipaddress
import sys

import yaml


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!secret", lambda loader, node: "<secret>")
Loader.add_constructor("!include", lambda loader, node: "<include>")

errors = []

common = yaml.load(open("firmware/common.yaml"), Loader=Loader)
defaults = common.get("substitutions", {})

stakes = {}   # node_name -> ip
for path in sorted(glob.glob("firmware/stakes/soil-stake-*.yaml")):
    subs = (yaml.load(open(path), Loader=Loader) or {}).get("substitutions", {})
    name, ip = subs.get("node_name"), str(subs.get("stake_ip", ""))
    gateway = str(subs.get("gateway", defaults.get("gateway")))
    mask = str(subs.get("subnet", defaults.get("subnet")))
    try:
        net = ipaddress.ip_network(f"{gateway}/{mask}", strict=False)
        addr = ipaddress.ip_address(ip)
    except ValueError as e:
        errors.append(f"{path}: {e}")
        continue
    if addr not in net:
        errors.append(f"{path}: stake_ip {ip} isn't in the network {net} (gateway {gateway}, subnet {mask})")
    if addr == ipaddress.ip_address(gateway):
        errors.append(f"{path}: stake_ip {ip} is the gateway's address")
    if ip in stakes.values():
        errors.append(f"{path}: stake_ip {ip} is used by another stake too")
    stakes[name] = ip

targets = {}  # board -> ip
for path in sorted(glob.glob("dashboard/prometheus/targets/*.yml")):
    for group in yaml.safe_load(open(path)) or []:
        board = (group.get("labels") or {}).get("board")
        for t in group.get("targets", []):
            targets[board] = t.rsplit(":", 1)[0]

for name, ip in stakes.items():
    if name not in targets:
        errors.append(f"{name} (stake_ip {ip}) isn't in dashboard/prometheus/targets/")
    elif targets[name] != ip:
        errors.append(f"{name}: firmware says {ip}, Prometheus list says {targets[name]}")
for board in targets:
    if board not in stakes:
        errors.append(f"{board} is in the Prometheus list but has no firmware/stakes/ file")

# ---- the Pi's planned address (deploy/site.env) ----
site = {}
for line in open("deploy/site.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        site[k] = v
pi_ip = None
try:
    pi = ipaddress.ip_interface(site["PI_STATIC_IP"])
    pi_ip = str(pi.ip)
    stake_net = ipaddress.ip_network(f"{defaults['gateway']}/{defaults['subnet']}", strict=False)
    if pi.network != stake_net:
        errors.append(f"deploy/site.env: PI_STATIC_IP {pi} isn't the stakes' network {stake_net}")
    if site.get("PI_GATEWAY") != str(defaults["gateway"]):
        errors.append(f"deploy/site.env: PI_GATEWAY {site.get('PI_GATEWAY')} differs from the stakes' gateway {defaults['gateway']}")
    if pi_ip == str(defaults["gateway"]):
        errors.append(f"deploy/site.env: PI_STATIC_IP {pi_ip} is the gateway's address")
    for name, ip in stakes.items():
        if ip == pi_ip:
            errors.append(f"deploy/site.env: PI_STATIC_IP {pi_ip} is also {name}'s stake_ip")
except (KeyError, ValueError) as e:
    errors.append(f"deploy/site.env: bad or missing PI_STATIC_IP ({e})")

if pi_ip:
    print(f"  {'Pi':<14} {pi_ip}")
for name, ip in stakes.items():
    print(f"  {name:<14} {ip}")
if errors:
    print("\n".join("ERROR: " + e for e in errors))
    sys.exit(1)
print(f"{len(stakes)} stakes: firmware and the Prometheus list agree; the Pi's address fits")
