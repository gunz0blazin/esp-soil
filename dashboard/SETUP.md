# Grow dashboard setup

Prometheus pulls readings straight from the ESP32 every 15 s and keeps 2 years of history. Grafana draws the graphs.

## 1. ESP32

In ESPHome Builder, add this to the board's YAML (anywhere at the top level, e.g. above `sensor:`), then Install:

```yaml
web_server:
  port: 80

prometheus:
```

Check it works: open `http://192.168.1.XXX/metrics` in a browser. You should see lines like
`esphome_sensor_value{id="soil_moisture",name="Soil moisture",...} 53`.

## 2. Server (Proxmox LXC/VM with Docker)

```bash
# copy this folder over, then:
cd dashboard
nano docker-compose.yml          # change GF_SECURITY_ADMIN_PASSWORD
nano prometheus/prometheus.yml   # check the board IP (192.168.1.XXX)
docker compose up -d
```

- Grafana: `http://<server-ip>:3000` (user `admin`). The **Grow Tent** dashboard opens as the home page.
- Prometheus: `http://<server-ip>:9090/targets` shows whether it can reach the board (should say **UP**).

Give the ESP32 a fixed IP in UniFi so the address in `prometheus.yml` never changes.

## 3. Phone

- Home Wi-Fi: open `http://<server-ip>:3000` and "Add to Home Screen". Panels stack into one column on a phone.
- Away from home: install Tailscale on the server and your phone, then use the server's Tailscale IP.
- Inside the HA app: Settings → Dashboards → Add dashboard → **Webpage**, URL `http://<server-ip>:3000/d/grow-tent?kiosk`.

## Adding soil stakes

Uncomment a stake block in `prometheus/prometheus.yml` for each stake, put in its IP, and run `docker compose restart prometheus`. The dashboard already looks for any sensor with "moisture", "temperature", "humidity" or "VPD" in its name, so the new plants fill in on their own.
