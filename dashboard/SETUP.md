# Dashboard setup (running it by hand)

Prometheus reads every stake's `/metrics` every 15 s and keeps 2 years of history. Grafana draws the graphs.

**On the site's Raspberry Pi you don't need this page.** The Pi deploys this folder automatically from `main`; see [`deploy/README.md`](../deploy/README.md). Use this page to run the same stack by hand on any Linux machine with Docker, for example to try a change before opening a pull request.

## 1. Stakes

The stake firmware (`firmware/common.yaml`) already serves `/metrics` behind the board login. Check a stake from the machine that will run Prometheus:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://<stake-ip>/metrics     # 401 = login is on
curl -s -u esp:<web_password> http://<stake-ip>/metrics | head       # readings come back
```

You should see lines like `esphome_sensor_value{id="moisture",name="Plant 1 moisture",unit="%"} 53`.

Give every stake a fixed IP (DHCP reservation) that matches `stake_ip` in its firmware file.

## 2. Start the stack

```bash
cd dashboard
nano prometheus/targets/stakes.yml                                  # one entry per stake: IP:80 + board label
printf '%s' '<web_password>' > prometheus/esp_web_password          # same as the stakes' web_password
chmod 644 prometheus/esp_web_password                               # Prometheus runs as "nobody" in the container
echo 'GRAFANA_ADMIN_PASSWORD=<pick-one>' > .env                     # only used the first time Grafana starts
docker compose up -d
```

Create `prometheus/esp_web_password` **before** the first `up`: if it's missing, Docker creates a folder with that name and every scrape fails. Both files are gitignored.

- Grafana: `http://<server-ip>:3000` (user `admin`). The **Soil Monitor** dashboard opens as the home page.
- Prometheus: `http://<server-ip>:9090/targets` shows whether it can reach each stake (should say **UP**). **401** means the password file doesn't match the stakes.

## 3. Phone

- On the same network: open `http://<server-ip>:3000` and "Add to Home Screen". Panels stack into one column on a phone.
- From anywhere: put the server on Tailscale and use its Tailscale name.
- Inside Home Assistant: Settings → Dashboards → Add dashboard → **Webpage**, URL `http://<server-ip>:3000/d/soil-monitor?kiosk`.

## Changes

| To | Do | Restart? |
|---|---|---|
| Add or remove a stake | Edit `prometheus/targets/stakes.yml` | No, picked up within a minute |
| Change scrape settings | Edit `prometheus/prometheus.yml` | `docker compose restart prometheus` |
| Change the board password | Update `prometheus/esp_web_password` | `docker compose restart prometheus` |
| Change the dashboard | Edit in Grafana, then export the JSON over `grafana/dashboards/soil-monitor.json` | No |
| Update Prometheus or Grafana | Change the pinned version in `docker-compose.yml` | `docker compose up -d` |

Don't run `docker compose down -v`: `-v` deletes the volumes, including all history.
