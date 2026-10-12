# Tailscale setup

Tailscale connects the site to home without opening any ports. The Pi joins your tailnet and acts as a **subnet router** for the site VLAN, so from home you can:

- flash and watch the stakes from the ESPHome add-on in Home Assistant
- have Home Assistant read the stakes over their encrypted API
- open Grafana and SSH on the Pi from your phone or laptop, anywhere

```
 Home                                   Tailscale (encrypted, outbound only)          Site VLAN 10.42.0.0/24
 Home Assistant + ESPHome add-on  ─────────────────────────────────────────►  Pi (10.42.0.10) ──► stakes 10.42.0.11–15
 phone / laptop                   ─────────────────────────────────────────►  Pi: Grafana :3000, SSH
```

The examples use the subnet `10.42.0.0/24`, the tags `tag:esp-soil-pi` and `tag:homeassistant`, and `you@example.com` for your Tailscale login. Swap in your own.

**Order matters:** set up the policy first (step 1), so the Pi and Home Assistant can be tagged when they join.

**Contents:** [1. Policy](#1-access-policy-first) · [2. Pi](#2-the-pi-subnet-router) · [3. Home Assistant](#3-home-assistant) · [4. Phone and laptop](#4-your-phone-and-laptop) · [5. Check it works](#5-check-it-works) · [Troubleshooting](#troubleshooting)

---

## 1. Access policy (first)

In the Tailscale admin console, open **Access controls** and edit the policy file.

> **Read this before saving.** A new tailnet allows every device to reach every other device. As soon as the policy has its own `acls` section, only what it lists is allowed. The first rule below keeps your own devices able to reach everything, as before. If you already have a custom policy, merge these sections into it instead of replacing it.

```jsonc
{
  // Who may apply each tag to a device.
  "tagOwners": {
    "tag:esp-soil-pi":    ["you@example.com"],
    "tag:homeassistant":  ["you@example.com"]
  },

  // Approve the Pi's route to the site VLAN automatically, no clicking needed.
  "autoApprovers": {
    "routes": {
      "10.42.0.0/24": ["tag:esp-soil-pi"]
    }
  },

  "acls": [
    // You (all your logged-in devices): everything, including the site VLAN.
    { "action": "accept", "src": ["you@example.com"], "dst": ["*:*"] },

    // Home Assistant: the whole stakes subnet (TCP, UDP and ping), nothing else.
    { "action": "accept", "src": ["tag:homeassistant"], "dst": ["10.42.0.0/24:*"] }
  ]
}
```

What this gives you:

| From | Can reach | Can't reach |
|---|---|---|
| Your phone and laptop | everything on the tailnet, the Pi (Grafana, SSH), the stakes | |
| Home Assistant | anything on the stakes' subnet | the Pi, your other devices |
| The Pi | nothing on the tailnet (it only answers) | everything |

Nothing at the site can start a connection into your home network.

---

## 2. The Pi (subnet router)

SSH into the Pi on the site network.

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

**Join the tailnet** as a tagged subnet router:

```bash
sudo tailscale up --advertise-tags=tag:esp-soil-pi --advertise-routes=10.42.0.0/24
```

It prints a login link. Open it, log in with your Tailscale account, and approve the device.

Because of the policy:

- The **route is approved automatically** (`autoApprovers`). Check the Pi's row on the **Machines** page: it shows a **Subnets** badge.
- **Key expiry is off automatically**, because tagged devices don't expire. That matters for a box nobody visits: an expired key would cut the site off until someone logs in on site. If you joined the Pi without a tag, turn it off by hand: Machines → the Pi's **…** menu → **Disable key expiry**.

**Give it a clear name:** on the Machines page, rename the Pi (for example `esp-soil-pi`). With MagicDNS (on by default) that name works as a hostname everywhere on your tailnet: `http://esp-soil-pi:3000` for Grafana, `ssh you@esp-soil-pi`.

**Notes**

- Don't add `--accept-routes` on the Pi. It doesn't need routes to your home network, and leaving it off keeps the site from reaching home.
- Raspberry Pi OS has no firewall by default. If you've added `firewalld`, Tailscale's docs say you may need `sudo firewall-cmd --permanent --add-masquerade`.
- To change the advertised route later: `sudo tailscale set --advertise-routes=<new-subnet>`.

---

## 3. Home Assistant

Install the **Tailscale** add-on (Settings → Add-ons → Add-on Store → Tailscale). **Before starting it**, open its **Configuration** tab and set:

| Option | Set to | Why |
|---|---|---|
| `userspace_networking` | **off** | **Required.** In the default userspace mode Home Assistant and its add-ons can't reach anything over the tailnet. Turning it off creates a real `tailscale0` interface on the host, which the ESPHome add-on uses too |
| `accept_routes` | **on** (default) | So Home Assistant learns the Pi's route to `10.42.0.0/24` |
| `tags` | `tag:homeassistant` | Matches the policy, so Home Assistant only gets the stake ports |
| `advertise_routes` | empty list | By default the add-on shares your home network with the tailnet. Nothing here needs that |
| `advertise_exit_node` | **off** | Not needed; on by default |
| `advertise_connector` | **off** | Not needed; on by default |

Leave everything else at its default. Then:

1. **Start** the add-on and open its logs.
2. Open its **Web UI** and log in to the same Tailscale account (the add-on's docs recommend Chrome on a desktop or laptop for this step).
3. Check the logs again: it should report it's connected.

Home Assistant is tagged, so its key doesn't expire either.

**Adding the stakes to Home Assistant:** discovery doesn't cross Tailscale, so add each one by IP: **Settings → Devices & services → Add integration → ESPHome**, enter the stake's IP (e.g. `10.42.0.11`), and paste the `api_key` when asked.

---

## 4. Your phone and laptop

Install the Tailscale app and log in with the same account.

- **Phones, Windows and macOS** use subnet routes automatically, so the stakes' IPs work too.
- **Linux laptops** need it switched on once: `sudo tailscale set --accept-routes`.

Then from anywhere:

| What | Address |
|---|---|
| Grafana | `http://esp-soil-pi:3000` |
| Prometheus | `http://esp-soil-pi:9090` |
| SSH to the Pi | `ssh you@esp-soil-pi` |
| A stake's web page | `http://10.42.0.11/` (asks for the board login) |

Bookmark Grafana on your phone's home screen for quick checks.

---

## 5. Check it works

From the **Home Assistant terminal** (Terminal & SSH add-on):

```bash
ip addr show tailscale0                                       # exists = userspace networking is off
curl -s -o /dev/null -w '%{http_code}\n' http://10.42.0.11/   # 401 = stake reached (it wants the login)
```

In the **ESPHome add-on**, **Logs → Wirelessly** on a stake streams its log. That's the real test: it connects straight to `stake_ip`.

The add-on's **Online/Offline** badge is a separate thing. By default the add-on decides it with mDNS, which doesn't cross Tailscale, so stakes can show **Offline** while logs and **Install → Wirelessly** work fine. If the badge bothers you, turn on ESPHome's ping-based status (it has been the `status_use_ping` option in the add-on's configuration; newer versions may have moved it into the dashboard's own settings). The policy in step 1 already allows ping.

On the Tailscale **Machines** page:

- the Pi has the **Subnets** badge, and its route is approved
- both the Pi and Home Assistant show their tags and have no expiry date

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl` from Home Assistant times out | Userspace networking is still on, or `accept_routes` is off | Check both options in the add-on, then restart it. `ip addr show tailscale0` must show the interface |
| Times out from everywhere | The route isn't approved, or forwarding isn't on | Machines → the Pi → Subnets; on the Pi, `sysctl net.ipv4.ip_forward` must print `1` |
| Works from your laptop, not from Home Assistant | The add-on isn't tagged, so the Home Assistant rule doesn't apply | Check the add-on's `tags` option matches the policy |
| Linux laptop can't reach the stakes | Linux doesn't accept routes by default | `sudo tailscale set --accept-routes` |
| ESPHome add-on shows a stake **Offline** but its logs work | The badge uses mDNS, which doesn't cross Tailscale | Harmless: installs and logs use `stake_ip` directly. To fix the badge, turn on ping-based status (see step 5) |
| Wireless logs or installs fail but `curl` works | `stake_ip` in the add-on's file is wrong | Check `stake_ip` matches the stake's fixed IP in UniFi |
| `tailscale up` says the tag isn't allowed | The tag isn't in `tagOwners` yet, or another user owns it | Save the policy from step 1 first, logged in as the tag owner |
| The site dropped off after a few months | The Pi's key expired (it joined without a tag) | On site: `sudo tailscale up --force-reauth`, then disable key expiry |
| Home network devices unreachable after adding the policy | The policy replaced the default allow-all | Keep the first rule (`you@example.com` → `*:*`), and add rules for anything else that used to work |
