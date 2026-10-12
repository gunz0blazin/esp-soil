# esp-soil

> **This is the `testing` branch.** It holds changes that are written but not yet running on the stakes or the dashboard server. `main` matches what's deployed right now. To see exactly what's new here, compare the branches: [`main...testing`](../../compare/main...testing). Once a change is flashed and checked on real hardware, it gets merged into `main` with a pull request.
>
> **In testing now**
> - **Board login:** the stake web page and `/metrics` require a username and password (`web_username` / `web_password` in `secrets.yaml`, HTTP basic auth). Prometheus logs in using a password file. Setup and checks are in [`dashboard/SETUP.md`](dashboard/SETUP.md#board-login-web-page--metrics).

Wi-Fi soil moisture stakes. Each stake is a small board with an ESP32-C3, a capacitive soil probe and an AHT10 temperature/humidity sensor in a 3D printed case. Push it into the soil like a plant marker and plug in a USB cable. It reports soil moisture, temperature, humidity and VPD over Wi-Fi to ESPHome / Home Assistant and Prometheus, and the included Grafana stack graphs it.

> **Status:** the breadboard version works and is graphing in Grafana. The stake PCB and snap-fit case are designed but haven't been built yet. The board is now a full KiCad project (`hardware/kicad/`) with the case in its 3D view. Run ERC/DRC there and plot Gerbers from it before ordering.

![stake board in the case, KiCad 3D models](docs/images/kicad-3d.png)

**Contents:** [What's in here](#whats-in-here) · [The stake](#the-stake) · [Setup](#setup) · [Calibrating](#calibrating) · [Data logging: Prometheus + Grafana](#data-logging-prometheus--grafana) ([Prometheus](#prometheus) · [Grafana](#grafana) · [Troubleshooting](#troubleshooting)) · [VPD](#vpd) · [Breadboard testing](#testing-on-a-breadboard)

---

## What's in here

```
firmware/
  soil-stake.yaml          the stake firmware (one per stake)
  moisture-test.yaml       breadboard test board: probe + AHT10 + OLED
  moisture-test-probe-only.yaml   same board, probe + OLED only
  legacy/                  the original 4-probe OLED + touch button build
hardware/
  kicad/                   KiCad project: schematic, PCB, 3D models + the case for fit checks
  pcb/                     v1 hand-made Gerbers, build guide PDF
  case/                    snap-fit case (3MF), OpenSCAD file, print notes
  legacy/                  case for the old 4-probe box
dashboard/                 Prometheus + Grafana in Docker, with the dashboard (see Data logging below)
secrets.example.yaml
```

---

## The stake

Each stake reads:

- Soil moisture %, calibrated to its own probe
- Raw probe voltage (for calibrating)
- Temperature and humidity
- Leaf VPD
- Wi-Fi signal

There's no screen. Everything goes to Grafana (see [Data logging](#data-logging-prometheus--grafana)), and there's a small web page on each stake at `http://<stake-ip>/` if you want a quick look.

### Parts (per stake)

| Part | Notes |
|---|---|
| Seeed XIAO ESP32-C3 | On 1x7 headers. Trim the pins under the board. Stick its FPC antenna to the inside of the lid |
| [DFRobot SEN0193](https://www.dfrobot.com/product-1385.html) capacitive soil probe | Cut off the JST plug, solder it straight to the board |
| AHT10 module | Check the pin order is VIN GND SCL SDA. Trim the header pins under the board |
| 10k + 33k resistors | Voltage divider, the C3's ADC tops out around 2.5 V |
| 0.1 µF ceramic cap | ADC noise filter |
| 100 µF electrolytic, 6.3 V+ | 5 mm across, 7 mm long max. Lay it flat |
| Stake PCB | 24 x 52 mm, 2 layers. KiCad project in `hardware/kicad/` |
| Printed case | `hardware/case/`, PETG |
| USB-C cable | Right-angle ones lie flat on the soil |

Everything is through-hole. Open `hardware/kicad/esp-soil-stake.kicad_pro` in KiCad 8+ for the schematic, the board and a 3D view with the case. [`hardware/kicad/README.md`](hardware/kicad/README.md) covers running the checks and making Gerbers. The assembly order is in `hardware/pcb/esp-soil-stake-build.pdf`. That PDF lists M2 screws, but the v2 case snaps together so you don't need them.

### Pins

| XIAO pin | Goes to |
|---|---|
| D1 / GPIO3 | Probe signal, through the 10k/33k divider |
| D4 / GPIO6 | AHT10 SDA |
| D5 / GPIO7 | AHT10 SCL |
| 3V3 / GND | AHT10 and probe power |

### Case

Two parts, snaps together, no screws. Both print without supports. The probe sticks out the bottom through a slot you seal with silicone, and USB-C comes out the top. Print notes and tuning are in [`hardware/case/PRINT-NOTES.md`](hardware/case/PRINT-NOTES.md).

![case preview](docs/images/case-preview.png)

### Power

It runs off USB, about 0.3 W per stake. A multi-port USB charger with a cable to each stake works well. Power banks aren't practical for long-term monitoring: 100 days would take 150,000+ mAh, and many power banks shut off at a draw this low anyway.

---

## Setup

You need [ESPHome](https://esphome.io/), either standalone or the Home Assistant add-on.

1. Copy `secrets.example.yaml` to `secrets.yaml` and fill in your Wi-Fi and the board login (`web_username` / `web_password`). It's in `.gitignore`.
2. Open `firmware/soil-stake.yaml` and change the top for each stake:
   ```yaml
   substitutions:
     plant: "1"            # stake number, used in the sensor names
     node_name: soil-stake-1
   ```
3. Flash over USB the first time. After that it updates over Wi-Fi.
   ```bash
   esphome run firmware/soil-stake.yaml
   ```
   Browser flashing (ESPHome Web) needs Chrome or Edge. Firefox doesn't do Web Serial.
4. Give each stake a fixed IP in your router.

---

## Calibrating

Out of the box the % means nothing. Every probe reads a little different, so each stake gets its own dry and wet value.

The probe voltage goes **down** as the soil gets wetter. On the stake you're reading it after the divider, so expect roughly 1.9 V dry and 0.9 V soaked.

1. Watch the stake's **raw** sensor (`Plant N raw`) in Grafana, the stake's web page, or the logs.
2. **Dry:** probe in the air or bone-dry mix. That's `dry_v`.
3. **Wet:** in the soil, watered until it drains, 30 minutes later. That's `wet_v`.
4. Put both in the substitutions and reflash.

0% means "as dry as the dry reference" and 100% means "right after a full watering." It's not actual water content, just a consistent scale.

### Keeping readings honest

- Same depth for every stake, and don't move a stake once it's calibrated. Moving it changes the reading.
- Press the soil firmly around the probe so there's no air gap.
- Only the probe below its line goes in the soil. The case keeps the electronics above it.
- Fertilizer salts slowly push readings up. If the numbers creep up for no reason, redo the wet value.
- The AHT10 sits right at soil level, so it reads warmer and more humid than the air higher up. The ESP also warms the board a bit. Compare against a thermometer you trust once and set the offset in the YAML.

---

## Data logging: Prometheus + Grafana

The stakes don't store any history themselves. A small Docker Compose stack in `dashboard/` does that:

- **Prometheus** visits every stake every 15 seconds, reads its current values from `http://<stake>/metrics`, and keeps them in a time-series database for 2 years.
- **Grafana** reads from Prometheus and draws the dashboard: current values at the top, history graphs below.

![How readings flow from a stake to Prometheus to Grafana](docs/images/data-flow.png)

Prometheus *pulls* from the stakes. A stake never sends data anywhere on its own, so if Prometheus is down, readings from that time just aren't recorded (the stakes keep running normally). Home Assistant is a separate path: it talks to each stake over the ESPHome native API and doesn't need Prometheus at all.

### What's in `dashboard/`

| File | What it does |
|---|---|
| `docker-compose.yml` | Runs Prometheus (port 9090) and Grafana (port 3000), with a named volume for each so data survives restarts and image updates |
| `prometheus/prometheus.yml` | Scrape settings and the list of stakes to read |
| `grafana/provisioning/datasources/prometheus.yml` | Connects Grafana to Prometheus automatically (no clicking through the UI) |
| `grafana/provisioning/dashboards/dashboards.yml` | Tells Grafana to load every dashboard JSON in `grafana/dashboards/` |
| `grafana/dashboards/*.json` | The dashboard itself |
| `SETUP.md` | Step-by-step install, phone access and adding stakes |

### Quick start

```bash
cd dashboard
nano docker-compose.yml          # set GF_SECURITY_ADMIN_PASSWORD (default is "changeme")
nano prometheus/prometheus.yml   # one target per stake, see below
docker compose up -d
```

- Grafana: `http://<server-ip>:3000`, user `admin`. The dashboard opens as the home page.
- Prometheus: `http://<server-ip>:9090`. Check **Status → Target health** first: every stake should say **UP**.

Any Linux machine, VM or container host on the same network as the stakes works. The whole stack is light: a few hundred MB of RAM, and storage is small (see [Storage and retention](#storage-and-retention)).

---

### What a stake sends

With `web_server:` and `prometheus:` in the firmware, each stake serves its sensor values as plain text at `/metrics`. You can open it in a browser or `curl` it:

```text
$ curl http://192.168.1.XXX/metrics
#TYPE esphome_sensor_value gauge
#TYPE esphome_sensor_failed gauge
esphome_sensor_value{id="probe_raw",name="Plant 1 raw",unit="V"} 1.455
esphome_sensor_failed{id="probe_raw",name="Plant 1 raw"} 0
esphome_sensor_value{id="moisture",name="Plant 1 moisture",unit="%"} 46
esphome_sensor_failed{id="moisture",name="Plant 1 moisture"} 0
...
```

Every sensor becomes one `esphome_sensor_value` line. The `name` label is the sensor's name from the YAML, and that's what the dashboard and the queries below match on. `esphome_sensor_failed` is `1` when a sensor has no valid reading (for example the AHT10 isn't responding). The exact set of labels can vary a little between ESPHome versions.

| Sensor (`name`) | Unit | How often the stake updates it |
|---|---|---|
| `Plant N raw` | V | every 10 s (median of the last 7 samples, sampled every 5 s) |
| `Plant N moisture` | % | every 10 s (calculated from the raw value) |
| `Plant N temperature` | °C | every 15 s |
| `Plant N humidity` | % | every 15 s |
| `Plant N leaf VPD` | kPa | every 15 s |
| `Plant N WiFi` | dBm | every 60 s |

`N` is the `plant` substitution set per stake in `firmware/soil-stake.yaml`. Prometheus scrapes every 15 s and records whatever the latest value is at that moment.

---

### Prometheus

#### Configuration

`dashboard/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s          # how often every stake is read

scrape_configs:
  - job_name: esphome
    metrics_path: /metrics
    static_configs:
      - targets:
          - 192.168.1.XXX:80    # the stake's IP and web_server port
        labels:
          board: soil-stake-1   # extra label so you can tell stakes apart
```

- **One `targets` block per stake.** The `board` label is added to every value from that stake, which makes queries and graphs easier to read.
- **Give every stake a fixed IP** (a DHCP reservation in your router). Prometheus has no way to find a stake whose address changed.
- **After editing the file**, apply it with `docker compose restart prometheus`. A restart doesn't lose any data.

Prometheus also adds two labels on its own: `job="esphome"` and `instance="<ip>:80"`. It also records a few series per stake about the scrape itself, the most useful being `up`, which is `1` when the last read worked and `0` when it didn't.

#### Checking the stakes are being read

Open `http://<server-ip>:9090/targets` (**Status → Target health**). Every stake should be **UP**, with a recent "Last scrape" time.

![Prometheus target health page with three stakes UP](docs/images/prometheus-targets.png)

If a stake shows **DOWN**, the error under it says why. The usual causes are in [Troubleshooting](#troubleshooting).

#### Querying

The **Query** page runs PromQL and can graph the result. This is useful for one-off questions the dashboard doesn't answer, and for testing a query before you put it in a Grafana panel.

![Prometheus query page graphing soil moisture for three stakes over 3 days](docs/images/prometheus-query.png)

*Sample data: three stakes over three days. Each sharp rise is a watering, followed by a slow dry-down.*

Queries that are handy for this project (all tested):

| What you want | PromQL |
|---|---|
| Current moisture, every stake | `esphome_sensor_value{name=~".*moisture"}` |
| Driest reading in the last 24 h | `min_over_time(esphome_sensor_value{name=~".*moisture"}[24h])` |
| Dry-down rate in % per hour (negative = drying) | `deriv(esphome_sensor_value{name=~".*moisture"}[1h]) * 3600` |
| Rough hours until a stake reaches 40% | `(esphome_sensor_value{name=~".*moisture"} - 40) / -(deriv(esphome_sensor_value{name=~".*moisture"}[3h]) * 3600) > 0` |
| Stakes that aren't responding | `up{job="esphome"} == 0` |
| Average temperature over the last day (°C) | `avg_over_time(esphome_sensor_value{name=~".*temperature"}[1d])` |
| Wi-Fi signal per stake | `esphome_sensor_value{name=~".*WiFi"}` |
| How many sensors each stake reports | `count by (board) (esphome_sensor_value)` |

The "hours until 40%" estimate only returns a value for stakes that are currently drying and are still above 40%. It's a straight-line projection from the last 3 hours, so treat it as a rough guide.

#### Storage and retention

- History is kept for **2 years** (`--storage.tsdb.retention.time=2y` in `docker-compose.yml`). Older data is deleted automatically.
- Data lives in the `prometheus-data` Docker volume, so it survives `docker compose restart`, `down`/`up` and image updates.
- Each stake produces about a dozen series at one sample every 15 s. Prometheus compresses this well, so two years for one stake comes to well under 100 MB.

---

### Grafana

#### Provisioning (set up from files)

Grafana is configured entirely from files in `dashboard/grafana/`, so a fresh install comes up ready to use:

- **Data source:** `provisioning/datasources/prometheus.yml` adds Prometheus at `http://prometheus:9090` (the container name on the Compose network) and makes it the default.
- **Dashboard:** `provisioning/dashboards/dashboards.yml` loads every JSON file in `grafana/dashboards/`. `docker-compose.yml` sets the bundled dashboard as Grafana's home page.
- **Other settings** (in `docker-compose.yml`): dark theme by default, and embedding is allowed so the dashboard can be shown inside a Home Assistant **Webpage** card.

UI edits to the dashboard are allowed and get saved in Grafana's own database. To keep a change for good (and in git), export it as JSON (**Export → Export as JSON**) and replace the file in `grafana/dashboards/`.

#### The dashboard

![Preview of the bundled Grafana dashboard with sample data](docs/images/grafana-dashboard-preview.png)

*Preview drawn from the dashboard file with sample data for three stakes. Panel layout, queries, units and color thresholds match the JSON; Grafana's own styling differs slightly.*

The default view is the last 24 hours, refreshing every 30 seconds.

**Right now** — stat tiles with the latest value, colored by threshold, and a sparkline of the time range:

| Panel | Shows | Colors |
|---|---|---|
| Soil moisture | Every `…moisture` sensor, one tile per stake | red under 30%, orange 30–45%, green 45–85%, blue 85%+ |
| Temperature | Every `…temperature` sensor, converted to °F | blue under 70, green 70–85, orange 85–90, red 90+ °F |
| Humidity | Every `…humidity` sensor | orange under 40%, green 40–70%, blue 70%+ |
| Leaf VPD | Every `…leaf…vpd` sensor | blue under 0.4, light green 0.4–0.8, green 0.8–1.2, purple 1.2–1.6, red 1.6+ kPa |
| Probe voltage | Every `…raw` sensor | none (for calibration) |

**Soil**

- **Soil moisture**: history for every stake, 0–100%, with a dashed line and red shading below 40%.
- **Probe raw voltage (calibration)**: the voltage behind each moisture reading. Use it to pick `dry_v` and `wet_v` (see [Calibrating](#calibrating)).

**Climate**

- **Temperature** (°F) with the 70–85 °F band shaded.
- **Humidity** (%).
- **VPD** (kPa) with the same color bands as the Leaf VPD tile.

#### How new stakes show up

The panels don't list stakes one by one. Each query matches sensor *names* with a case-insensitive pattern, for example:

```promql
esphome_sensor_value{name=~"(?i).*moisture.*"}
```

So as soon as Prometheus is reading a new stake, its moisture, temperature, humidity, VPD and raw voltage appear on the dashboard with no Grafana changes. This also means a sensor needs one of those words in its name to be picked up.

#### Known limitations

- **Temperature, Humidity and Leaf VPD tiles** use fixed legend text (`Temp`, `RH`, `Leaf VPD`), so with several stakes every tile has the same label. The order matches the stake order, but it's easy to mix up. The moisture and voltage panels show the full sensor name.
- **Leaf VPD tile vs VPD graph:** the tile matches `leaf…vpd`, the graph matches any sensor with `vpd` in its name. With the stake firmware they show the same sensors.
- Short gaps (a stake rebooting, a missed scrape) are bridged on the graphs if they're under 5 minutes. Longer gaps show as breaks.

---

### Viewing on a phone or remotely

- **On your home network:** open `http://<server-ip>:3000` and use "Add to Home Screen". Panels stack into one column on a narrow screen.
- **Away from home:** use a VPN to your network (for example Tailscale or WireGuard) rather than opening ports 3000 or 9090 to the internet.
- **Inside Home Assistant:** add a **Webpage** card or dashboard pointing at `http://<server-ip>:3000/d/<dashboard-uid>?kiosk`. The UID is the `uid` field in the dashboard JSON. `?kiosk` hides Grafana's menus.

More detail is in [`dashboard/SETUP.md`](dashboard/SETUP.md).

### Security notes

- **The stakes have no login.** Anyone on your network can open a stake's web page or `/metrics` and see its readings.
- **Change the Grafana admin password** in `docker-compose.yml` before the first start. It's `changeme` by default.
- **Prometheus (9090) has no login.** Keep it on your local network.

### Maintenance

| Task | How |
|---|---|
| Add a stake | Add a `targets` block to `prometheus/prometheus.yml`, then `docker compose restart prometheus` |
| Remove a stake | Delete its block and restart Prometheus. Its old history stays until it ages out |
| Update Prometheus and Grafana | `docker compose pull && docker compose up -d`. Both images use the `latest` tag; pin a version in `docker-compose.yml` if you'd rather update on your own schedule |
| Back up the history | Stop Prometheus (`docker compose stop prometheus`), copy the `prometheus-data` volume (on most installs it's named `dashboard_prometheus-data`), then start it again |
| Reset Grafana settings | Remove the `grafana-data` volume. The data source and dashboard come back from the provisioning files on the next start |

Don't run `docker compose down -v` unless you mean it: `-v` deletes both volumes, including all history.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Target **DOWN**, "connection refused" or timeout | Stake is off, on a different IP, or not on Wi-Fi | Check the stake's IP in your router and open `http://<ip>/metrics` from the server |
| Target **DOWN**, "404 Not Found" | Firmware is missing `prometheus:` | Add `web_server:` and `prometheus:` to the YAML and reflash |
| Target **UP** but the stake isn't on the dashboard | Sensor names don't contain `moisture`, `temperature`, `humidity`, `vpd` or `raw` | Check the names at `/metrics` |
| Whole dashboard says "No data" | Grafana can't reach Prometheus | Both containers must be in the same Compose stack; check **Connections → Data sources → Prometheus → Test** |
| History is gone after a restart | A volume was removed | Use `restart` or `down`/`up`, not `down -v` |
| Graph times look shifted | Grafana uses the browser's time zone | Change it in the dashboard settings or your Grafana profile |

---

## VPD

Leaf VPD (vapor pressure deficit) is calculated from the AHT10's temperature and humidity. It assumes the leaf surface is slightly cooler than the air; the offset is `leaf_offset_c` in the YAML, default 2 °C.

---

## Testing on a breadboard

`firmware/moisture-test.yaml` is the pre-PCB test build: an ESP32 DevKit with one probe, an AHT10 and a 0.96" OLED showing moisture, temp, RH and VPD.

| Part | ESP32 pin |
|---|---|
| Probe signal | GPIO32 |
| OLED SDA / SCL | GPIO21 / GPIO22 |
| AHT10 SDA / SCL | GPIO25 / GPIO26 |

Lessons from the breadboard build:

- **Keep probes on ADC1 pins (GPIO32–35).** ADC2 stops working when Wi-Fi is on.
- **Give the AHT10 its own I2C bus.** It can lock up a shared bus and take the OLED down with it.
- **Check your OLED's pin order.** Some are GND-VCC-SCL-SDA and some are VCC-GND-SCL-SDA.
- **Cheap probes:** look at the chip. You want **TLC555**, not **NE555**. The NE555 ones don't behave at 3.3 V.
- **No probes yet?** A 10k potentiometer works: outer legs to 3V3 and GND, middle leg to the probe pin. Turn it and watch the % move.

The original 4-probe box with touch buttons is still in `firmware/legacy/` and `hardware/legacy/` if anyone wants a single-box version.

---

## License

See [`LICENSE`](LICENSE).
