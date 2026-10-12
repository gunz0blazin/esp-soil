# esp-soil

> **This is the `testing` branch.** It holds changes that are written but not yet running on the stakes or the dashboard server. `main` matches what's deployed right now. To see exactly what's new here, compare the branches: [`main...testing`](../../compare/main...testing). Once a change is flashed and checked on real hardware, it gets merged into `main` with a pull request.
>
> **In testing now**
> - **Board login:** the stake web page and `/metrics` require a username and password (`web_username` / `web_password` in `secrets.yaml`, HTTP basic auth). Prometheus logs in using a password file. Setup and checks are in [`dashboard/SETUP.md`](dashboard/SETUP.md#board-login-web-page--metrics).

Wi-Fi soil moisture stakes. Each stake is a small board with an ESP32-C3, a capacitive soil probe and an AHT10 temperature/humidity sensor in a 3D printed case. Push it into the soil like a plant marker and plug in a USB cable. It reports soil moisture, temperature, humidity and VPD over Wi-Fi to ESPHome / Home Assistant and Prometheus, and the included Grafana stack graphs it.

> **Status:** the breadboard version works and is graphing in Grafana. The stake PCB and snap-fit case are designed but haven't been built yet. The board is now a full KiCad project (`hardware/kicad/`) with the case in its 3D view. Run ERC/DRC there and plot Gerbers from it before ordering.

![stake board in the case, KiCad 3D models](docs/images/kicad-3d.png)

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
dashboard/                 Prometheus + Grafana in Docker, with the dashboard
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

There's no screen. Everything goes to Grafana, and there's a small web page on each stake at `http://<stake-ip>/` if you want a quick look.

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

## Grafana dashboard

`dashboard/` is a Docker Compose stack: Prometheus scrapes each stake's `/metrics` every 15 s and keeps 2 years of data, and Grafana draws the graphs. The dashboard picks up any sensor with "moisture", "temperature", "humidity" or "VPD" in its name, so new stakes show up on their own.

```bash
cd dashboard
nano docker-compose.yml          # change the Grafana admin password
nano prometheus/prometheus.yml   # add your stakes' IPs
docker compose up -d
```

Grafana is on `:3000`. More detail, including viewing it on your phone, is in [`dashboard/SETUP.md`](dashboard/SETUP.md).

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
