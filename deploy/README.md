# Deploying ESP-Soil

How changes get from this repo to a running site: a Raspberry Pi that runs Prometheus and Grafana, plus the soil stakes. The Pi can be on a network you don't control; everything it does is an outbound connection.

**Contents:** [How a change gets deployed](#how-a-change-gets-deployed) · [1. Set up the Pi](#1-set-up-the-pi) · [2. Tailscale](#2-tailscale-reach-the-site-from-home) ([full guide](TAILSCALE.md)) · [3. ESPHome in Home Assistant](#3-esphome-in-home-assistant) · [4. Day to day](#4-day-to-day) · [Troubleshooting](#troubleshooting)

---

## How a change gets deployed

```
  work on `testing` ──► pull request into `main` ──► GitHub checks run
                                                        │ all green
                                                        ▼
                                                  merge to `main`
                                   ┌────────────────────┴────────────────────┐
                                   ▼                                         ▼
                 dashboard/ changed: the Pi deploys itself       firmware/ changed: you flash from the
                 within ~5 min and sends a notification          ESPHome add-on (canary first, then the rest)
```

| What changed | What happens | You do |
|---|---|---|
| `dashboard/` (Prometheus, Grafana, list of stakes) | The Pi notices the new commit on `main` within about 5 minutes, validates it, deploys it, and notifies you | Nothing |
| `firmware/` | Nothing automatic. The ESPHome add-on in Home Assistant shows the change on the next build | Flash one stake, check it, then the rest ([4. Day to day](#flashing-firmware)) |
| `deploy/` | The Pi updates its own deploy command and timer on the next run | Nothing |
| Anything else (docs, hardware) | The Pi runs and finds nothing to change | Nothing |

**Why firmware isn't automatic:** server changes are frequent and easy to undo. A bad firmware update on a site you're not at can mean a trip with a USB cable, so a person picks when it happens and watches the first stake come back. It's still always the merged code: each stake's file in the add-on pulls `firmware/common.yaml` from `main` at build time.

### What the GitHub checks cover

`.github/workflows/checks.yml` runs on every push to `testing` and `main` and on every pull request into `main`. It uses throwaway secrets and never deploys, so it's safe on a public repo.

| Check | What it proves |
|---|---|
| Firmware | Every stake file and the Home Assistant stub validate with ESPHome (pinned version), and the firmware compiles |
| Dashboard | Prometheus config passes `promtool`; compose file is valid; the targets file is well formed with no duplicate stakes; the pinned images exist and have ARM64 builds for the Pi |
| Deploy | The playbook runs end to end on the runner (validate, sync, start the stack, health checks), and a second run changes nothing; Grafana loads the dashboard; Prometheus finds every stake in the targets file |

---

## 1. Set up the Pi

### Hardware and OS

- Raspberry Pi with 2 GB RAM or more. The stack uses well under 1 GB. The Pi never compiles firmware.
- **Storage:** Prometheus writes all the time, which wears out ordinary SD cards. Boot from a USB SSD, or use a high-endurance card. 32 GB is plenty.
- **OS:** Raspberry Pi OS Lite, 64-bit. Set the hostname, user, SSH key and network in Raspberry Pi Imager.
- PoE or USB-C power, and a wired connection to the site's network if possible.

### Run the bootstrap

SSH into the Pi:

```bash
git clone https://github.com/gunz0blazin/esp-soil.git /tmp/esp-soil
sudo /tmp/esp-soil/deploy/bootstrap.sh
```

It asks for:

| Prompt | What to enter |
|---|---|
| Stake web_password | The same `web_password` that's in the ESPHome `secrets.yaml`. Prometheus logs in to the stakes with it |
| Grafana admin password | Your choice. Used the first time Grafana starts |
| ntfy topic URL | Optional. Where deploy notifications go, e.g. `https://ntfy.sh/<long-random-topic>`. Press Enter to skip |

Then it:

1. Installs git, rsync, Ansible, and Docker (from Docker's official repository).
2. Saves the secrets in `/etc/esp-soil/`, readable only by root.
3. Installs `esp-soil-deploy` and a systemd timer that runs it every 5 minutes.
4. Runs the first deploy. Pulling the images takes a few minutes the first time.
5. Sets up **Tailscale** as a subnet router for the site VLAN: installs it, turns on IP forwarding, and shares the subnet the Pi is on (e.g. `10.42.0.0/24`) under the name `esp-soil-pi`. It prints a login link; open it and log in. At the end it reminds you of the two clicks left in the Tailscale admin console: approve the route, and disable key expiry. Details: [`TAILSCALE.md`](TAILSCALE.md).

Options:

| To | Run |
|---|---|
| Skip it | `sudo deploy/bootstrap.sh --no-tailscale` |
| Share a different subnet | `sudo TS_ROUTES=10.50.0.0/24 deploy/bootstrap.sh` |
| Use another tailnet name | `sudo TS_HOSTNAME=soil-site-pi deploy/bootstrap.sh` (default `esp-soil-pi`; in a container, the container's hostname) |
| Deploy a branch other than the one you cloned | `sudo BRANCH=testing deploy/bootstrap.sh` |
| Log in without a browser | `sudo TS_AUTHKEY=tskey-... deploy/bootstrap.sh` (an auth key from the admin console) |

The passwords are shown as you type them, so you can check them before pressing Enter.

When it finishes, it checks that Prometheus and Grafana are answering, tries the Grafana login, and prints a summary:

```
================================================================
 ESP-Soil on esp-soil-pi  (Raspberry Pi (…))
 Deploys branch 'main' every 5 minutes  (journalctl -u esp-soil-deploy)
----------------------------------------------------------------
 Grafana     [running]
   http://10.42.0.10:3000
   http://esp-soil-pi:3000  /  http://100.x.y.z:3000   (tailnet)
   user: admin    password: …
   (login checked, works)

 Prometheus  [running]
   http://10.42.0.10:9090
   …
 Stakes (web page + /metrics, used by Prometheus)
   user: esp    password: …
================================================================
```

Grafana opens with the **Soil Monitor** dashboard as its home page. If something isn't running, the script says so and exits with an error. Running the bootstrap again is safe: it skips what's done and never overwrites a secret.

### Secrets on the Pi

Everything secret lives in `/etc/esp-soil/` and never goes in git:

| File | Used for | Required |
|---|---|---|
| `esp_web_password` | Prometheus logging in to the stakes | Yes |
| `grafana_admin_password` | Grafana's admin password on first start | Yes |
| `ntfy_url` | Deploy notifications (full topic URL) | No |
| `ntfy_token` | Access token, if your ntfy topic is protected | No |
| `deploy.env` | Which repo and branch to deploy (`BRANCH=`, the branch you cloned) | Created by bootstrap |

To change one, edit the file (`sudo nano /etc/esp-soil/esp_web_password`, no trailing newline needed) and run `sudo esp-soil-deploy --force`.

**Grafana's password** is only applied when Grafana starts with an empty database. After that, change it in Grafana (profile → change password) and update the file to match, so a rebuild uses the same one.

**Notifications:** install the ntfy app on your phone and subscribe to the same topic. Anyone who knows a public topic name can read it, so use a long random name, or a protected topic with `ntfy_token`. You get one notification per deploy:

- ✅ **ESP-Soil deployed**: the commit, and how many stakes Prometheus can reach (with the names of any that are down)
- ❌ **ESP-Soil deploy FAILED** (high priority): the commit and the step that failed

### How the deploy works

`esp-soil-deploy` runs `ansible-pull`: it pulls `main` into `/opt/esp-soil/src` and, **only if there are new commits**, runs [`site.yml`](site.yml). The playbook:

1. Checks the secrets exist.
2. **Validates before touching anything live**: runs `promtool` on the new Prometheus config and checks the compose file. If either fails, the running stack is left exactly as it was.
3. Syncs `dashboard/` into `/opt/esp-soil/dashboard` (removed files are removed there too), and writes the secrets in next to it.
4. Runs `docker compose up -d`. Prometheus or Grafana is restarted only if its own config changed. Changes to the list of stakes need no restart at all.
5. Waits until Prometheus and Grafana are healthy, and gives Prometheus up to a minute to scrape every stake once.
6. Updates its own deploy command and timer from the repo, then notifies you.

| | Path |
|---|---|
| Repo checkout used by the deploy | `/opt/esp-soil/src` |
| Running stack (compose project `esp-soil`) | `/opt/esp-soil/dashboard` |
| Prometheus history | Docker volume `esp-soil_prometheus-data` |
| Grafana settings | Docker volume `esp-soil_grafana-data` |

### Useful commands on the Pi

```bash
sudo esp-soil-deploy --force                  # deploy now, showing every step's output
sudo esp-soil-deploy --force -vv              # even more detail; --quiet for task names only
systemctl list-timers esp-soil-deploy.timer   # when it last ran / runs next
journalctl -u esp-soil-deploy -n 100          # output of recent deploys
cd /opt/esp-soil/dashboard && sudo docker compose -p esp-soil ps     # container status
cd /opt/esp-soil/dashboard && sudo docker compose -p esp-soil logs -f prometheus
```

### Running on a container or VM

The bootstrap detects where it's running and says so (`Running on: Raspberry Pi …`, `container (lxc)`, `virtual machine (kvm)`). In a **container** it adjusts:

- The tailnet name defaults to the container's own hostname, so a test box never takes the real Pi's `esp-soil-pi` name.
- If `/dev/net/tun` is missing, it skips Tailscale and says so. A container can't grant itself the TUN device: pass it through from the container's host, then rerun the bootstrap.
- If Docker can't start, it says the container needs nesting enabled on its host.
- If the container can't turn on IP forwarding, it warns instead of failing.

### Testing the pipeline on a spare Pi

The bootstrap deploys **the branch you cloned**, so a test Pi just needs a clone of `testing`:

```bash
git clone -b testing https://github.com/gunz0blazin/esp-soil.git /tmp/esp-soil
sudo /tmp/esp-soil/deploy/bootstrap.sh
```

It prints `This Pi will deploy branch: testing`, and from then on that Pi deploys every push to `testing` within 5 minutes. That's a full rehearsal of the site setup before anything reaches `main`. Keep the site Pi on `main` (clone `main`, or the default branch).

To move a Pi to another branch later, either rerun the bootstrap from a clone of that branch, set it explicitly with `sudo BRANCH=main /tmp/esp-soil/deploy/bootstrap.sh`, or edit `BRANCH=` in `/etc/esp-soil/deploy.env` and run `sudo esp-soil-deploy --force`.

---

## 2. Tailscale: reach the site from home

The Pi joins your tailnet and acts as a **subnet router** for the stakes' network. Your home Home Assistant (and its ESPHome add-on) can then reach the stakes as if they were local: flash them, read their logs, and add them to Home Assistant. You also get Grafana and SSH on the Pi from anywhere. Nothing at the site needs port forwarding.

### Pick the stakes' subnet

The Pi and the stakes get **their own VLAN at the site, with addresses decided in advance**. Pick a subnet that doesn't overlap your home network (or routing over Tailscale breaks) and isn't a common default like `192.168.1.0/24`. The examples in this repo use **`10.42.0.0/24`**:

| Device | Address |
|---|---|
| Gateway (the VLAN's router interface) | `10.42.0.1` |
| Raspberry Pi | `10.42.0.10` |
| Stakes 1–5 | `10.42.0.11`–`10.42.0.15` |

Give each device its address with a **DHCP reservation** on the VLAN (by MAC address). That keeps the addresses in one place: the stake firmware doesn't need to know the gateway or DNS, and you can move the VLAN later without reflashing. A stake's MAC address is in the add-on's logs on its first boot, or in the router's client list.

Then keep these three in step whenever a stake's address changes:

- `stake_ip` in its firmware file (`firmware/stakes/` and the add-on)
- `dashboard/prometheus/targets/stakes.yml`
- its DHCP reservation

**Wi-Fi:** give the VLAN its own SSID on 2.4 GHz (the ESP32-C3 has no 5 GHz) with WPA2-PSK. Use that SSID and password for `wifi_ssid` / `wifi_password` in the add-on's secrets. WPA3-only can be unreliable with ESP32 boards, so allow WPA2.

**Router rules: as few as possible.**

- **No port forwards, no UPnP, no allow rules.** Tailscale connects outbound from the Pi and works through NAT by itself; nothing reaches the site from the internet.
- **The Pi and the stakes are on the same VLAN,** so their traffic never passes through the router's firewall. Home Assistant's traffic arrives through the Pi's Tailscale route, so to the VLAN it's local too.
- The Pi needs ordinary outbound internet (GitHub, Docker Hub, Tailscale, ntfy), which a new VLAN has by default.
- **Optional, one toggle:** turn on **Isolate Network** for the VLAN in UniFi. It blocks the VLAN from your other networks without writing rules.
- **Leave client device isolation off** on the stakes' SSID, so the stakes and the Pi can talk to each other.

### Setting it up

The full step-by-step guide is in **[`TAILSCALE.md`](TAILSCALE.md)**. It uses Tailscale's default open policy, so every device on your tailnet reaches the Pi and the stakes as if they were on your own network. In short:

1. **Pi:** install Tailscale, turn on IP forwarding, `sudo tailscale up --advertise-routes=10.42.0.0/24`.
2. **Admin console:** approve the Pi's subnet route, and **disable key expiry** on the Pi and Home Assistant (otherwise the site drops off in a few months).
3. **Home Assistant:** Tailscale add-on with **`userspace_networking` off** (required, or nothing in Home Assistant can reach the stakes), `accept_routes` on, and its own route and exit-node advertising off.
4. **Check:** from the Home Assistant terminal, `curl -s -o /dev/null -w '%{http_code}\n' http://10.42.0.11/` prints `401`.

---

## 3. ESPHome in Home Assistant

You keep using the ESPHome add-on's dashboard for flashing, logs and status. Each stake is a small file in the add-on; the firmware itself comes from `main`.

### secrets.yaml in the add-on

Open the add-on, then **Secrets** (top right), and add the values from [`secrets.example.yaml`](../secrets.example.yaml):

```yaml
wifi_ssid: "the-stakes-wifi"
wifi_password: "..."
web_username: "esp"
web_password: "..."      # same as /etc/esp-soil/esp_web_password on the Pi
api_key: "..."           # python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
```

`api_key` encrypts both the Home Assistant connection and every firmware update. **Keep a copy somewhere safe** (a password manager). If it's lost, a stake can only be updated by USB, and the key can't be changed over the air.

### One file per stake

For each stake, create a new device in the add-on (**+ New device**, name it `soil-stake-1` and so on), open it with **Edit**, and replace everything with [`firmware/ha-stub.example.yaml`](../firmware/ha-stub.example.yaml). Then change the values at the top:

```yaml
substitutions:
  plant: "1"
  node_name: soil-stake-1
  stake_ip: 10.42.0.11
  dry_v: "1.92"
  wet_v: "0.92"
```

The `packages:` block at the bottom fetches `firmware/common.yaml` from `main` on GitHub every time you build (`refresh: 0s`), so you never copy firmware by hand, and only merged code can be flashed.

### First flash (USB, before the stakes go to the site)

1. Plug the stake into the computer running your browser, then in the add-on: the device's menu → **Install** → **Plug into this computer**. Browser flashing needs Chrome or Edge.
2. Calibrate (see [Calibrating](../README.md#calibrating)), update `dry_v` / `wet_v`, and install again over Wi-Fi.
3. In Home Assistant: **Settings → Devices & services → Add integration → ESPHome**, enter the stake's IP, and paste the `api_key` when asked. Discovery doesn't work across Tailscale, so add stakes by IP.

---

## 4. Day to day

### Making a change

1. Work on `testing` (or a branch off it) and push. The checks run on every push.
2. Open a pull request from `testing` into `main`. The checks run again; merge when they're green. Use **Create a merge commit** (not squash), so `testing` can catch up without a force-push.
3. Let `testing` catch up with `main` so it's back to showing only new, unmerged work:
   ```bash
   git checkout testing && git pull && git merge --ff-only origin/main && git push
   ```
4. Dashboard changes are live within about 5 minutes; watch for the notification. For firmware changes, see below.

**Recommended GitHub settings** (Settings → Branches → add a rule for `main`): require a pull request before merging, and require the status checks **Firmware (ESPHome)**, **Dashboard (Prometheus + Grafana)** and **Deploy playbook (dry run on the runner)** to pass. That makes the checks a real gate instead of advice.

### Flashing firmware

After a merge that changed `firmware/`:

1. In the add-on, **Install → Wirelessly** on **one** stake (the canary).
2. Watch its logs until it reconnects. Check it shows up **UP** in Prometheus and its readings look right in Grafana.
3. Then install on the rest, one by one or with **Update All**.

If the canary doesn't come back, stop there. ESPHome's safe mode usually lets you reflash it over the network after a few failed boots. If not, it needs USB at the site. The other stakes are still on the old, working firmware.

### Adding a stake

1. Pick its number and IP, and add a DHCP reservation for it.
2. Add `firmware/stakes/soil-stake-N.yaml` (copy another stake's file) and an entry in `dashboard/prometheus/targets/stakes.yml`. Merge.
3. Create its file in the add-on from the stub, flash it by USB, and add it to Home Assistant by IP.
4. Prometheus picks it up after the merge deploys, and the dashboard shows it automatically.

### Changing the stakes' web password

1. Change `web_password` in the add-on's secrets and install on every stake.
2. Put the same password in `/etc/esp-soil/esp_web_password` on the Pi and run `sudo esp-soil-deploy --force`.

Stakes show **DOWN (401)** in Prometheus between steps 1 and 2, so do both in one sitting.

### Rolling back

- **Dashboard:** revert the commit on `main` (GitHub has a **Revert** button on merged pull requests). The Pi deploys the revert like any other change.
- **Firmware:** revert on `main`, then reinstall the stakes from the add-on.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No deploy notification after a merge | Notifications not set up, timer not running, or the deploy failed before notifying | `systemctl list-timers esp-soil-deploy.timer` and `journalctl -u esp-soil-deploy -n 100` |
| "deploy FAILED at: Validate Prometheus config" | The new `prometheus.yml` or targets file is invalid. The running stack is unchanged | Fix it on `testing`; the checks would have caught it if they're required on `main` |
| "deploy FAILED at: Stop if a secret is missing" | A file in `/etc/esp-soil/` is missing | Recreate it, then `sudo esp-soil-deploy --force` |
| Failed deploy, then nothing happens | The timer only deploys new commits | Fix and merge, or run `sudo esp-soil-deploy --force` |
| Notification says stakes are down | Stake off, out of Wi-Fi range, or its IP changed | Check DHCP reservations; open `http://<stake-ip>/` from the Pi |
| Stakes **DOWN (401)** | Password on the stakes and on the Pi don't match | [Changing the stakes' web password](#changing-the-stakes-web-password) |
| Add-on shows the stake **Offline**, but Prometheus has it UP | Usually just the badge: it uses mDNS, which doesn't cross Tailscale. If wireless logs also fail, Home Assistant can't reach the route | See [TAILSCALE.md, step 5](TAILSCALE.md#5-check-it-works) and its troubleshooting |
| Add-on install fails with an encryption error | Stake firmware older than ESPHome 2026.9, or a different `api_key` | Update the add-on; check `api_key` matches what the stake was flashed with. Otherwise flash by USB |
| Add-on build says ESPHome is too old | `min_version` in `common.yaml` | Update the ESPHome add-on |
