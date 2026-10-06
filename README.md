# esp-soil

A little ESP32 box that sits in my grow tent and tells me when the plants need water. It reads four soil moisture probes and an AHT10 for temp and humidity, works out VPD, and shows everything on a cheap 0.96" OLED. Two touch buttons flip between screens. It also shows up in Home Assistant through ESPHome, so I get graphs and phone alerts.

I built it because "water when it starts to wilt" was a bad system, and weighing pots wasn't consistent enough. My partner helps with watering, so I wanted something you can just glance at.

> **Status:** works on the bench with test pots. Running it on a real grow next. Expect some rough edges.

---

## What it does

- Soil moisture % for 4 pots, each calibrated to its own probe
- A big **WATER** flag next to any pot that drops below the trigger
- Tent temperature (°F and °C) and humidity
- Air VPD and leaf VPD, plus a label for which stage it's good for
- Watering trigger is a slider in Home Assistant, so no reflashing to tweak it
- Everything gets logged in Home Assistant

### Screens

Tap **Next** or **Back** to cycle:

| Screen | Shows |
|---|---|
| Moisture | P1–P4 %, with OK or WATER for each |
| Temperature | Big °F reading, °C underneath, 70–85 °F target |
| Humidity | Big % reading, veg and flower targets |
| VPD | Leaf VPD in kPa, the zone it's in, and air VPD |

---

## Parts

| Part | Qty | Notes |
|---|---|---|
| ESP32 DevKit V1 (30-pin) | 1 | Any ESP32 dev board should work, just double check pin labels |
| [DFRobot SEN0193](https://www.dfrobot.com/product-1385.html) capacitive soil moisture sensor | 4 | ~$6 each. Get a spare. |
| AHT10 temp/humidity module | 1 | I had a pile of these. An AHT20 or SHT40 would be better if you're buying new. |
| SSD1306 0.96" OLED, I2C, 128x64 | 1 | The common $5 one |
| TTP223 touch button | 1–2 | Second one is optional |
| 0.1 µF ceramic caps | 4 | Optional, helps with noisy readings |
| Jumper wires / breadboard or perfboard | | |
| 3D printed case | 1 | See `case/` |

Cheap generic capacitive probes work fine for testing. If you go that route, look at the chip on the board: you want **TLC555**, not **NE555**. The NE555 ones don't behave at 3.3V.

---

## Wiring

Full diagram is in [`docs/grow-monitor-wiring.pdf`](docs/grow-monitor-wiring.pdf). Short version:

| Part | Pin | ESP32 |
|---|---|---|
| Plant 1 probe | SIG | GPIO32 |
| Plant 2 probe | SIG | GPIO33 |
| Plant 3 probe | SIG | GPIO34 |
| Plant 4 probe | SIG | GPIO35 |
| AHT10 | SDA / SCL | GPIO25 / GPIO26 |
| OLED | SDA / SCL | GPIO21 / GPIO22 |
| Touch "Next" | I/O | GPIO27 |
| Touch "Back" | I/O | GPIO14 |

Everything gets VCC from **3V3** and shares **GND**.

Some stuff I learned the annoying way:

- **Keep the probes on GPIO32–35.** Those are ADC1. The ADC2 pins stop working as soon as Wi-Fi turns on.
- **The AHT10 gets its own I2C bus.** It doesn't play nice with other devices and can lock up the bus, which takes the OLED down with it. That's why it's on 25/26 and the OLED is on 21/22.
- **Check your OLED's pin order.** Some are GND-VCC-SCL-SDA and some are VCC-GND-SCL-SDA.
- Unconnected ADC pins read random garbage, so ignore those rows (or tie them to GND) while testing.

---

## Setup

You need [ESPHome](https://esphome.io/) installed, either standalone or the Home Assistant add-on.

1. Clone the repo:
   ```bash
   git clone https://github.com/<you>/grow-moisture.git
   cd grow-moisture
   ```

2. Make a `secrets.yaml` next to the config:
   ```yaml
   wifi_ssid: "your-wifi"
   wifi_password: "your-password"
   api_key: "generate-one-at-esphome.io"
   ota_password: "something"
   fallback_password: "something-else"
   ```
   It's in `.gitignore`. Don't commit it.

3. Check the config, then flash over USB the first time:
   ```bash
   esphome config grow-moisture.yaml
   esphome run grow-moisture.yaml
   ```
   After that you can update it over Wi-Fi.

4. Home Assistant should find it automatically. Add it and you'll see all the sensors.

---

## Calibrating the probes

Out of the box the % numbers mean nothing. Every probe reads a little different, so each one needs its own dry and wet value.

These probes put out a voltage that goes **down** as the soil gets wetter, roughly 2.5 V dry and 1.2 V soaked.

1. Flash it and watch the **Plant N raw** sensors in Home Assistant (or the logs).
2. **Dry value:** probe in dry mix, or just in the air. Write down the voltage.
3. **Wet value:** put the probe in its pot, water to runoff, wait 30 minutes, and write it down.
4. Put the numbers at the top of `grow-moisture.yaml`:
   ```yaml
   substitutions:
     p1_dry: "2.42"
     p1_wet: "1.31"
   ```
5. Reflash.

Now 0% means "as dry as my reference" and 100% means "right after a full watering." It's not actual water content, just a consistent scale.

### Setting the water trigger

The first time a plant starts to droop, check what % it's at. Set the **Water trigger** slider in Home Assistant to somewhere between a third and halfway from that number up to 100%. It defaults to 40%.

### Keeping readings honest

- Put every probe at the same depth, about halfway down and 2–3" from the stem
- Don't move them during the grow. Moving one changes the reading.
- Press the soil firmly around the probe so there's no air gap
- Only the part below the line on the board goes in the soil. Seal the electronics on top with heat shrink or conformal coating.
- Fertilizer salts slowly push readings up. If the numbers drift up for no reason, redo the wet value.

---

## Testing without probes

Waiting on parts? Hook up a 10k potentiometer per channel: outer legs to 3V3 and GND, middle leg to the probe pin. Turning it sweeps the voltage, so you can watch the % move and the WATER flag kick in.

Two resistors work too if you don't have pots:

| Pretend | R1 (to 3V3) | R2 (to GND) | ~Volts |
|---|---|---|---|
| Dry | 3.3k | 10k | 2.48 |
| Halfway | 10k | 10k | 1.65 |
| Wet | 10k | 5.6k | 1.18 |

A bare capacitor won't work as a fake probe. The probe module measures capacitance on its own board and just outputs a voltage, so a voltage is what you need to fake.

---

## VPD

VPD is calculated from the AHT10 temp and humidity:

- **Air VPD** uses air temperature only
- **Leaf VPD** assumes the leaves are a bit cooler than the air, which is normal under LEDs. The offset is `leaf_offset_c` in the config, default 2 °C.

Rough zones the screen uses:

| Leaf VPD (kPa) | Label |
|---|---|
| under 0.4 | TOO LOW |
| 0.4 – 0.8 | seedling / clone |
| 0.8 – 1.2 | veg |
| 1.2 – 1.6 | flower |
| over 1.6 | TOO HIGH |

If your AHT10 reads off compared to a hygrometer you trust, there are commented-out `offset` filters in the config to fix it.

---

## Case

`case/grow-moisture-case.scad` is a parametric OpenSCAD case. It has a box and lid, an OLED window, a USB opening, a slot for the probe cables, vents, and zip-tie ears for strapping it to a tent pole.

1. Measure your ESP32 and OLED with calipers. Boards vary a lot between sellers.
2. Fix the values marked `MEASURE` at the top of the file.
3. Set `part = "box"`, render (F6), export STL. Do the same with `part = "lid"`.
4. Print at 0.2 mm, no supports. Box open side up, lid face down.

Hardware: 4× M3 x 8 mm self-tappers for the lid, 4× M2 x 5 mm for the OLED. If the lid is too tight, bump `fit` from 0.3 to 0.4.

Heads up: I haven't printed this version yet, so check the dimensions before you burn filament on it.

---

## Repo layout

```
grow-moisture/
├── grow-moisture.yaml        # ESPHome config
├── secrets.yaml              # yours, not committed
├── case/
│   └── grow-moisture-case.scad
└── docs/
    └── grow-monitor-wiring.pdf
```

---

## To do

- [ ] RS485 soil EC probe in one pot to watch salt buildup ([DFRobot SEN0601](https://www.dfrobot.com/product-2817.html))
- [ ] Float switch in the drain pan so I get a "go empty it" alert
- [ ] IR leaf temp sensor (MLX90614) for real leaf VPD instead of a guess
- [ ] Print and test the case
- [ ] Home Assistant dashboard and alerts

---

## License

MIT. Do whatever you want with it. If you build one and improve it, I'd like to see it.
