# Stake PCB: KiCad project

The full stake board as a KiCad project: schematic, PCB, footprints, 3D models for every part, and the snap-fit case loaded into the 3D viewer, so you can check the fit before ordering anything.

![3D preview](source/render-3d.png)

## Opening it

1. Install KiCad 8 or newer (kicad.org). It's saved in KiCad 8 format, so 8, 9 and 10 all open it.
2. Open `esp-soil-stake.kicad_pro`.
3. Everything is self-contained. The symbols, footprints and 3D models live in this folder (`esp-soil.kicad_sym`, `esp-soil.pretty/`, `3d/`) and are hooked up through the project's own library tables. Nothing needs installing.

## Running the checks in KiCad

**Schematic (ERC):** open the schematic, then **Inspect → Electrical Rules Checker → Run ERC**. You should get 0 errors. Unused XIAO pins have no-connect flags, and GND has a PWR_FLAG.

**PCB (DRC):** open the PCB, then **Inspect → Design Rules Checker**. Leave **Refill all zones** ticked and turn on **Test for parity between PCB and schematic**, then **Run DRC**.

- The GND pour on the back isn't pre-filled. DRC fills it, or press **B** in the PCB editor.
- The rules are set for a cheap 2-layer fab (JLCPCB/PCBWay): 0.2 mm clearance, 0.3 mm copper to edge. You can see them under **File → Board Setup → Design Rules**.
- KiCad may warn that the XIAO's courtyard goes past the board edge. That's on purpose: the USB-C port overhangs by 1.4 mm so the cable reaches it through the case's top opening.

**3D fit with the case:** in the PCB editor, **View → 3D Viewer** (Alt+3). The case is a 3D-only part called `CASE1`. The back shell is solid and the lid is see-through, so you can look inside.

- To hide part of the case: in the PCB editor, hover over the `CASE OUTLINE` box on the F.Fab layer and press **E** to open CASE1's properties. On the **3D Models** tab, untick **Show** for the shell or the lid.

## Making Gerbers

Once ERC and DRC are clean: **File → Fabrication Outputs → Gerbers (.gbr)**, then **Generate Drill Files** in the same dialog. Zip the folder and upload it to the fab.

The hand-made Gerbers in `../pcb/` are the v1 board. This project is v1.1 and is the one to order from now on. The routing is the same; the differences are:

- The resistors and C1 use KiCad's stock footprints (slightly smaller pads, and C1's legs are 2.5 mm apart).
- The board text moved to the back silkscreen.

## Parts

| Ref | Part | Footprint | Notes |
|---|---|---|---|
| U1 | Seeed XIAO ESP32-C3 | `XIAO_ESP32C3_THT` | On 1x7 male headers. Pin map and spacing come from Seeed's own KiCad library. **Plug in the FPC antenna that comes with it.** The C3 has no antenna on the board. |
| J1 | AHT10 breakout (VIN GND SCL SDA) | `AHT10_Module_1x04_P2.54mm` | On its own 4-pin header |
| P1 | DFRobot SEN0193, 98 x 23 mm | `SEN0193_Wire_Pads_1x03_P2.54mm` | Cut the JST plug off, solder the leads: A = signal, + = 3V3, − = GND |
| R1 | 10k, 1/4 W (small, DIN0204) | KiCad `R_Axial_DIN0204..._Vertical` | Stands up |
| R2 | 33k, 1/4 W (small, DIN0204) | same | Stands up |
| C1 | 100 nF ceramic disc | KiCad `C_Disc_D3.0mm_W1.6mm_P2.50mm` | |
| C2 | 100 µF 6.3 V+ electrolytic, **5 mm across, 7 mm long max** | `CP_Radial_D5.0mm_P2.50mm_LaidFlat_L7mm` | Bend it flat toward the AHT10 |
| H1, H2 | 2.2 mm holes | `MountingHole_2.2mm_M2` | The case's locating pins go through these |
| CASE1 | Case v2 | 3D-only | Not a real part. It's excluded from the BOM and position files. |

## What's been checked

`source/verify_kicad.py` checks the project independently, without KiCad: **33 checks pass, 0 fail.** The full output is in `source/verify-report.txt`.

- **Files:** every file parses as valid KiCad syntax. The board, schematic, symbols and footprints all load in [kiutils](https://github.com/mvnmgrx/kiutils), a separate KiCad file parser.
- **Schematic:** connections are rebuilt from the actual pin and wire positions. No dangling wires, and every pin is either connected or flagged no-connect. Power nets are driven.
- **Schematic vs. board:** every pad's net matches the schematic, and footprints and symbols match one-to-one.
- **Board:**
  - Every net is fully routed. GND runs through the back pour.
  - Clearances: the smallest pad-to-pad gap is 0.37 mm and the smallest track-to-pad gap is 0.97 mm. Rings and edge clearance are all inside the rules.
  - No courtyard overlaps.
- **Fit in the real case geometry**, at 0.2 mm resolution:
  - No part touches the case.
  - The board rests on its ledges and posts. The lid bosses clamp it, and the only case material passing through the board is the two pins in H1/H2.
  - A full-size USB-C plug reaches the port.
  - The probe clears its slot.
  - There's about 21 x 27 mm of room on the lid's underside over the probe for the antenna.

The checker also gives two build notes:

- **Trim the header pins under the board.** Standard male headers stick out about 4.4 mm under the PCB, and the case only allows about 2.7 mm. Snip them after soldering, the same as the resistor leads.
- **Stick the XIAO's FPC antenna** to the underside of the lid over the probe end, away from the AHT10 vents.

## Measure these before ordering

These sizes came from datasheets and listings, not from your parts:

- **AHT10 module:** modeled as 16.1 x 11.2 mm with the header along the long edge. Breakouts vary. If yours is bigger, check it clears the lid boss beside H2: there's about 1.3 mm of room past the module's far edge.
- **C2:** 100 µF caps come in 5 x 7, 5 x 11 and 6.3 x 5 mm. Laid flat, there's room for a body up to about 7.5 mm long.
- **XIAO:** modeled at 21 x 17.8 mm with a 1.2 mm PCB, sitting on a 2.5 mm header spacer.

## Regenerating

Everything here is generated, so change the generator rather than editing the files by hand. If you do edit in KiCad, that's fine; just don't rerun the generator afterward or it will overwrite your changes.

```bash
cd source
python3 gen_kicad.py      # rewrites the project + 3D models (reads ../../case/source/gen_case.py for the case)
python3 verify_kicad.py   # all the checks above, exit code 1 on failure
python3 render_3d.py      # render-3d.png
```

They need numpy, scikit-image and matplotlib; `pip install kiutils` for the extra parser check.

## Credits

- The XIAO pin map and spacing come from [Seeed Studio's OPL KiCad library](https://github.com/Seeed-Studio/OPL_Kicad_Library).
- The resistor and C1 footprints and 3D models are KiCad's stock libraries ([kicad-footprints](https://github.com/KiCad/kicad-footprints), [kicad-packages3D](https://github.com/KiCad/kicad-packages3D)), CC-BY-SA 4.0 with KiCad's library exception.
- The XIAO, AHT10, probe and C2 models are simple block models made for the fit check, not detailed parts.
