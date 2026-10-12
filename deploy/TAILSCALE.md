# Tailscale setup

Tailscale connects the site to your tailnet without opening any ports. The Pi joins your tailnet and acts as a **subnet router** for the site VLAN, so every device on your tailnet can reach the Pi **and** the stakes as if they were sitting on your own network:

- the ESPHome add-on in Home Assistant flashes the stakes and streams their logs
- Home Assistant reads the stakes over their encrypted API
- your phone or laptop opens Grafana, Prometheus, SSH on the Pi, or a stake's web page, from anywhere

```
 Your tailnet (home, phone, laptop)        Tailscale (encrypted, outbound only)          Site VLAN 10.42.0.0/24
 Home Assistant + ESPHome add-on  ─────────────────────────────────────────►  Pi (10.42.0.10) ──► stakes 10.42.0.11–15
 phone / laptop / anything else   ─────────────────────────────────────────►  Pi: Grafana :3000, SSH
```

This uses Tailscale's **default, open policy**: every device on your tailnet can reach every other one, with no access rules to write. The examples use the subnet `10.42.0.0/24`; swap in your own.

**Contents:** [1. Pi](#1-the-pi-subnet-router) · [2. Admin console](#2-admin-console) · [3. Home Assistant](#3-home-assistant) · [4. Phone and laptop](#4-your-phone-and-laptop) · [5. Check it works](#5-check-it-works) · [Troubleshooting](#troubleshooting)

---

## 1. The Pi (subnet router)

**`deploy/bootstrap.sh` does this whole step for you**: it installs Tailscale, turns on forwarding, works out the VLAN's subnet from the Pi's address, and runs `tailscale up` with the route and the name `esp-soil-pi`. Open the login link it prints, then go to [step 2](#2-admin-console). See [`README.md`](README.md#run-the-bootstrap) for its options.

The manual steps, if you skipped it (`--no-tailscale`) or want to know what it does. SSH into the Pi on the site network.

**Install Tailscale:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

**Let the Pi forward traffic** between the tailnet and the VLAN:

```bash
echo 'net.ipv4.ip_forward = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
```

**Join the tailnet and share the VLAN:**

```bash
sudo tailscale up --advertise-routes=10.42.0.0/24 --hostname=esp-soil-pi
```

It prints a login link. Open it and log in with your Tailscale account.

**Notes**

- Don't add `--accept-routes` on the Pi. It doesn't need routes to anything else, and leaving it off keeps the Pi from routing into other networks your tailnet shares.
- Raspberry Pi OS has no firewall by default. If you've added `firewalld`, Tailscale's docs say you may need `sudo firewall-cmd --permanent --add-masquerade`.
- To change the shared subnet later: `sudo tailscale set --advertise-routes=<new-subnet>`.

---

## 2. Admin console

On the **Machines** page of the Tailscale admin console:

1. **Approve the route.** The Pi shows a **Subnets** badge. Open the Pi → **Subnets** → **Edit**, tick `10.42.0.0/24`, and save. Until you do, nothing can reach the stakes.
2. **Disable key expiry** on the Pi: its **…** menu → **Disable key expiry**. **Don't skip this.** Keys expire after a few months by default, and an expired key cuts the site off until someone logs in on site.
3. Check it's called **`esp-soil-pi`** (the bootstrap sets that name). With MagicDNS (on by default) that name works as a hostname everywhere on your tailnet.

Do step 2 for Home Assistant too once it's joined (step 3 below).

**If you've already written a custom access policy** for your tailnet, the open default isn't in effect. Make sure your policy lets your devices reach the Pi and `10.42.0.0/24`.

---

## 3. Home Assistant

Install the **Tailscale** add-on (Settings → Add-ons → Add-on Store → Tailscale). **Before starting it**, open its **Configuration** tab and set:

| Option | Set to | Why |
|---|---|---|
| `userspace_networking` | **off** | **Required.** In the default userspace mode, Home Assistant and its add-ons can't reach anything over the tailnet. Turning it off creates a real `tailscale0` interface on the host, which the ESPHome add-on uses too |
| `accept_routes` | **on** (default) | So Home Assistant learns the Pi's route to `10.42.0.0/24` |
| `advertise_routes` | empty list | By default the add-on shares your home network into the tailnet. The site doesn't need that, and leaving it off keeps the site from reaching your home network |
| `advertise_exit_node` | **off** | Not needed; on by default |
| `advertise_connector` | **off** | Not needed; on by default |

Leave everything else at its default. Then:

1. **Start** the add-on and open its logs.
2. Open its **Web UI** and log in to the same Tailscale account (the add-on's docs recommend Chrome on a desktop or laptop for this step).
3. Check the logs again: it should report it's connected.
4. Back in the admin console, **Disable key expiry** for Home Assistant too.

**Adding the stakes to Home Assistant:** discovery doesn't cross Tailscale, so add each one by IP: **Settings → Devices & services → Add integration → ESPHome**, enter the stake's IP (e.g. `10.42.0.11`), and paste the `api_key` when asked.

---

## 4. Your phone and laptop

Install the Tailscale app on anything you want to reach the site from, and log in with the same account.

- **Phones, Windows and macOS** use subnet routes automatically.
- **Linux machines** need it switched on once: `sudo tailscale set --accept-routes`.

Then from anywhere:

| What | Address |
|---|---|
| Grafana | `http://esp-soil-pi:3000` |
| Prometheus | `http://esp-soil-pi:9090` |
| SSH to the Pi | `ssh you@esp-soil-pi` |
| A stake's web page | `http://10.42.0.11/` (asks for the board login) |
| Anything else on the site VLAN | its `10.42.0.x` address |

Bookmark Grafana on your phone's home screen for quick checks.

---

## 5. Check it works

From the **Home Assistant terminal** (Terminal & SSH add-on):

```bash
ip addr show tailscale0                                       # exists = userspace networking is off
curl -s -o /dev/null -w '%{http_code}\n' http://10.42.0.11/   # 401 = stake reached (it wants the login)
```

In the **ESPHome add-on**, **Logs → Wirelessly** on a stake streams its log. That's the real test: it connects straight to `stake_ip`.

The add-on's **Online/Offline** badge is a separate thing. By default the add-on decides it with mDNS, which doesn't cross Tailscale, so stakes can show **Offline** while logs and **Install → Wirelessly** work fine. If the badge bothers you, turn on ESPHome's ping-based status (it has been the `status_use_ping` option in the add-on's configuration; newer versions may have moved it into the dashboard's own settings).

On the Tailscale **Machines** page:

- the Pi has the **Subnets** badge, and the route is approved
- the Pi and Home Assistant both show **Expiry disabled**

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Bootstrap says Tailscale was **skipped, /dev/net/tun is missing**, or `tailscaled` won't start in a Proxmox container | LXC containers don't get the TUN device by default (a real Pi always has it) | On the Proxmox host: `curl -fsSL https://raw.githubusercontent.com/gunz0blazin/esp-soil/main/deploy/proxmox-lxc-setup.sh \| sh -s -- <container-id>` ([what it does](proxmox-lxc-setup.sh)), then rerun the bootstrap |
| `curl` from Home Assistant times out | Userspace networking is still on, or `accept_routes` is off | Check both options in the add-on, then restart it. `ip addr show tailscale0` must show the interface |
| Times out from everywhere | The route isn't approved, or forwarding isn't on | Machines → the Pi → Subnets; on the Pi, `sysctl net.ipv4.ip_forward` must print `1` |
| Linux machine can't reach the stakes | Linux doesn't accept routes by default | `sudo tailscale set --accept-routes` |
| The Pi answers, the stakes don't | A custom access policy is blocking the subnet | Allow your devices to reach `10.42.0.0/24` in the policy, or go back to the default |
| ESPHome add-on shows a stake **Offline** but its logs work | The badge uses mDNS, which doesn't cross Tailscale | Harmless: installs and logs use `stake_ip` directly. To fix the badge, turn on ping-based status (see step 5) |
| Wireless logs or installs fail but `curl` works | `stake_ip` in the add-on's file is wrong | Check `stake_ip` matches the stake's fixed IP in UniFi |
| The site dropped off after a few months | The Pi's key expired | On site: `sudo tailscale up --force-reauth`, then disable key expiry |
