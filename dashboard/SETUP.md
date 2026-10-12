# Grow dashboard setup

Prometheus pulls readings straight from the ESP32 every 15 s and keeps 2 years of history. Grafana draws the graphs.

## 1. ESP32

In ESPHome Builder, add this to the board's YAML (anywhere at the top level, e.g. above `sensor:`), then Install:

```yaml
web_server:
  port: 80

prometheus:
```

Check it works: open `http://192.168.1.162/metrics` in a browser. You should see lines like
`esphome_sensor_value{id="soil_moisture",name="Soil moisture",...} 53`.

## 2. Server (Proxmox LXC/VM with Docker)

```bash
# copy this folder over, then:
cd dashboard
nano docker-compose.yml          # change GF_SECURITY_ADMIN_PASSWORD
nano prometheus/prometheus.yml   # check the board IP (192.168.1.162)
docker compose up -d
```

- Grafana: `http://<server-ip>:3000` (user `admin`). The **Grow Tent** dashboard opens as the home page.
- Prometheus: `http://<server-ip>:9090/targets` shows whether it can reach the board (should say **UP**).

Give the ESP32 a fixed IP in UniFi so the address in `prometheus.yml` never changes.

## Board login (web page + /metrics)

The firmware puts a username/password on each board's web page, and that login also covers `/metrics`, so Prometheus has to log in too. Use the same password everywhere.

1. In ESPHome's `secrets.yaml` (the HA add-on's config folder), add:
   ```yaml
   web_username: "grow"
   web_password: "your-long-password"
   ```
   Then flash/OTA each board.
2. On the Prometheus server, create the password file **before** starting or restarting the stack. If it's missing, Docker creates a folder with that name instead and every scrape fails.
   ```bash
   cd dashboard
   printf '%s' 'your-long-password' > prometheus/esp_web_password
   chmod 644 prometheus/esp_web_password   # Prometheus runs as user "nobody" inside the container
   docker compose up -d --force-recreate prometheus
   ```
   The username in `prometheus/prometheus.yml` (`grow`) must match `web_username`.
3. Check it:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' http://<board-ip>/metrics              # 401 = login is on
   curl -s -u grow:your-long-password http://<board-ip>/metrics | head             # metrics come back
   ```
   And `http://<server-ip>:9090/targets` should show every board **UP**. A **401** there means the password file doesn't match the board.

Boards still on firmware without a login ignore the credentials, so you can flash them one at a time.

## 3. Phone

- Home Wi-Fi: open `http://<server-ip>:3000` and "Add to Home Screen". Panels stack into one column on a phone.
- Away from home: install Tailscale on the server and your phone, then use the server's Tailscale IP.
- Inside the HA app: Settings → Dashboards → Add dashboard → **Webpage**, URL `http://<server-ip>:3000/d/grow-tent?kiosk`.

## Adding soil stakes

Uncomment a stake block in `prometheus/prometheus.yml` for each stake, put in its IP, and run `docker compose restart prometheus`. The dashboard already looks for any sensor with "moisture", "temperature", "humidity" or "VPD" in its name, so the new plants fill in on their own.
