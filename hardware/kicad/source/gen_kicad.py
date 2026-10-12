"""Generate the ESP-Soil stake KiCad project (KiCad 8 file format; opens in KiCad 8, 9 and 10).

Writes, next to this folder:
  esp-soil-stake.kicad_pro / .kicad_sch / .kicad_pcb
  esp-soil.kicad_sym, esp-soil.pretty/  (project-local symbol + footprint library)
  sym-lib-table, fp-lib-table
  3d/  (part models + the snap-fit case, VRML)
  3d/bodies.json (part volumes, used by verify_kicad.py)

Run:  python3 gen_kicad.py      (needs numpy + scikit-image, same as the case generator)
Board coordinates: PCB top-left corner at (100, 100), y down, mm. Same layout as the v1 Gerbers.
"""
import os, uuid, math, json, re
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
CASE_SRC = os.path.join(PROJ, "..", "case", "source", "gen_case.py")
NAME, LIB = "esp-soil-stake", "esp-soil"
OX, OY = 100.0, 100.0          # board origin in KiCad
W, H = 24.0, 52.0              # board size
REV = "1.1"
DATE = "2026-10-11"

def U(*k):  # deterministic UUIDs so regenerating doesn't churn git diffs
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "esp-soil-stake/" + "/".join(map(str, k))))
ROOT = U("root")
def f(v): return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) > 1e-9 else "0"
def q(s): return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'

# ===================================================================== nets
NETS = ["", "GND", "+3V3", "/ADC", "/SDA", "/SCL", "/PROBE_A"]
def net_id(n):
    if n not in NETS: NETS.append(n)
    return NETS.index(n)

# ===================================================================== footprints
# A footprint def: name, descr, attr, pads[(num, kind, shape, x, y, size, drill, pinname, pintype)],
# graphics[(type, layer, data, width)], texts[(text, x, y, layer, size)], models[(file, offset, rot)],
# bodies[(label, x0,y0,z0, x1,y1,z1)] (local mm, z up from board top) for the 3D fit check.
FP = {}

def xiao_fp():
    pins = [(n, f"D{n-1}") for n in range(1, 8)] + [(8, "D7"), (9, "D8"), (10, "D9"), (11, "D10"),
                                                     (12, "3V3"), (13, "GND"), (14, "5V")]
    types = {"3V3": "power_out", "GND": "power_in", "5V": "power_in"}
    pads = []
    for n, nm in pins:
        x, y = (-7.62, -7.62 + 2.54*(n-1)) if n <= 7 else (7.62, 7.62 - 2.54*(n-8))
        pads.append((str(n), "thru_hole", "rect" if n == 1 else "circle", x, y, 1.7, 1.0, nm,
                     types.get(nm, "bidirectional")))
    g = [("rect", "F.Fab", (-8.9, -10.55, 8.9, 10.425), 0.1),
         ("rect", "F.Fab", (-4.47, -11.9, 4.47, -4.55), 0.1),          # USB-C receptacle (overhangs the edge)
         ("rect", "F.SilkS", (-8.75, -10.2, 8.75, 10.5), 0.12),
         ("rect", "F.CrtYd", (-9.15, -12.15, 9.15, 10.7), 0.05)]
    t = [("XIAO ESP32-C3", 0, -0.5, "F.SilkS", 1.0), ("^ USB-C UP ^", 0, 1.75, "F.SilkS", 0.9),
         ("${REFERENCE}", 0, 4.5, "F.Fab", 1.0)]
    b = [("header plastic L", -8.89, -8.89, 0, -6.35, 8.89, 2.5),
         ("header plastic R", 6.35, -8.89, 0, 8.89, 8.89, 2.5),
         ("header pins below board L", -7.94, -7.94, -3.1, -7.30, 7.94, 0),
         ("header pins below board R", 7.30, -7.94, -3.1, 7.94, 7.94, 0),
         ("header pins above XIAO L", -7.94, -7.94, 3.7, -7.30, 7.94, 5.5),
         ("header pins above XIAO R", 7.30, -7.94, 3.7, 7.94, 7.94, 5.5),
         ("XIAO PCB", -8.9, -10.55, 2.5, 8.9, 10.425, 3.7),
         ("XIAO USB-C receptacle", -4.47, -11.9, 3.7, 4.47, -4.55, 6.96),
         ("XIAO parts (ESP32-C3, LDO, buttons)", -7.0, -4.0, 3.7, 7.0, 9.0, 5.2),
         ("XIAO U.FL antenna jack", 4.5, -9.5, 3.7, 7.5, -6.5, 4.95)]
    return dict(name="XIAO_ESP32C3_THT", descr="Seeed XIAO ESP32-C3 on 2.54mm male headers. Pad map and spacing from Seeed's OPL KiCad library (XIAO-ESP32-C3-DIP), drawn USB-up",
                attr="through_hole", pads=pads, graphics=g, texts=t, ref=(0, 6.5, "F.Fab"),
                models=[("xiao_esp32c3.wrl", (0, 0, 0), (0, 0, 0))], bodies=b)

def aht_fp():
    pads = [(str(i+1), "thru_hole", "rect" if i == 0 else "circle", -3.81 + 2.54*i, 0, 1.7, 1.0, nm, ty)
            for i, (nm, ty) in enumerate([("VIN", "power_in"), ("GND", "power_in"), ("SCL", "input"), ("SDA", "bidirectional")])]
    g = [("rect", "F.Fab", (-8.05, -1.3, 8.05, 9.9), 0.1),
         ("rect", "F.CrtYd", (-8.3, -1.55, 8.3, 10.15), 0.05)]
    t = [("V", -3.81, 1.65, "F.SilkS", 0.8), ("G", -1.27, 1.65, "F.SilkS", 0.8),
         ("C", 1.27, 1.65, "F.SilkS", 0.8), ("D", 3.81, 1.65, "F.SilkS", 0.8),
         ("AHT10", 0, -2.9, "F.SilkS", 1.0), ("${REFERENCE}", 0, 5, "F.Fab", 1.0)]
    b = [("header plastic", -5.08, -1.27, 0, 5.08, 1.27, 2.5),
         ("header pins below board", -4.13, -0.32, -3.1, 4.13, 0.32, 0),
         ("AHT10 module PCB (assumed 16.1 x 11.2 mm)", -8.05, -1.3, 2.5, 8.05, 9.9, 4.1),
         ("AHT10 sensor", -2.0, 2.3, 4.1, 2.0, 7.3, 5.7)]
    return dict(name="AHT10_Module_1x04_P2.54mm", descr="Common AHT10 breakout (VIN GND SCL SDA), on its own 4-pin male header. Board size assumed 16.1 x 11.2 mm: measure yours",
                attr="through_hole", pads=pads, graphics=g, texts=t, ref=(5.6, -2.9, "F.SilkS"),
                models=[("aht10_module.wrl", (0, 0, 0), (0, 0, 0))], bodies=b)

def probe_fp():
    pads = [(str(i+1), "thru_hole", "rect" if i == 0 else "circle", -2.54 + 2.54*i, 0, 1.8, 1.0, nm, ty)
            for i, (nm, ty) in enumerate([("SIG", "output"), ("VCC", "power_in"), ("GND", "power_in")])]
    g = [("rect", "F.CrtYd", (-3.9, -1.25, 3.9, 1.25), 0.05),
         ("rect", "F.Fab", (-11.5, 5.5, 11.5, 103.5), 0.1)]     # the probe itself, hanging off the bottom edge
    t = [("A", -2.54, -1.95, "F.SilkS", 0.9), ("+", 0, -1.95, "F.SilkS", 0.9), ("-", 2.54, -1.95, "F.SilkS", 0.9),
         ("PROBE", 7.0, 1.4, "F.SilkS", 0.8)]
    b = [("probe leads", -3.0, 0.0, 0.0, 3.0, 5.6, 0.6),
         ("SEN0193 probe board (98 x 23 mm)", -11.5, 5.5, -1.6, 11.5, 103.5, 0.0),
         ("SEN0193 electronics", -6.0, 6.5, 0.0, 6.0, 20.0, 2.0)]
    return dict(name="SEN0193_Wire_Pads_1x03_P2.54mm", descr="DFRobot SEN0193 capacitive soil probe, JST removed, leads soldered to A/+/-. Probe drawn on F.Fab",
                attr="through_hole", pads=pads, graphics=g, texts=t, ref=(-7.5, 1.1, "F.SilkS"),
                models=[("sen0193_probe.wrl", (0, 0, 0), (0, 0, 0))], bodies=b)

def r_fp():  # KiCad stock Resistor_THT:R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical
    pads = [("1", "thru_hole", "circle", 0, 0, 1.4, 0.7, "", "passive"),
            ("2", "thru_hole", "oval", 2.54, 0, 1.4, 0.7, "", "passive")]
    g = [("circle", "F.Fab", (0, 0, 0.8), 0.1), ("line", "F.Fab", (0, 0, 2.54, 0), 0.1),
         ("circle", "F.SilkS", (0, 0, 0.92), 0.12), ("line", "F.SilkS", (0.92, 0, 1.54, 0), 0.12),
         ("rect", "F.CrtYd", (-1.05, -1.05, 3.49, 1.05), 0.05)]
    return dict(name="R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical", descr="KiCad stock footprint (Resistor_THT), 1/4W-small resistor standing up",
                attr="through_hole", pads=pads, graphics=g, texts=[("${REFERENCE}", 1.27, -1.92, "F.Fab", 1.0)],
                ref=(1.27, -1.92, "F.SilkS"), models=[("R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical.wrl", (0, 0, 0), (0, 0, 0))],
                bodies=None, wrl_bbox="R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical.wrl")

def c_fp():  # KiCad stock Capacitor_THT:C_Disc_D3.0mm_W1.6mm_P2.50mm
    pads = [("1", "thru_hole", "circle", 0, 0, 1.6, 0.8, "", "passive"),
            ("2", "thru_hole", "circle", 2.5, 0, 1.6, 0.8, "", "passive")]
    g = [("rect", "F.Fab", (-0.25, -0.8, 2.75, 0.8), 0.1),
         ("line", "F.SilkS", (0.621, -0.92, 1.879, -0.92), 0.12), ("line", "F.SilkS", (0.621, 0.92, 1.879, 0.92), 0.12),
         ("rect", "F.CrtYd", (-1.05, -1.05, 3.55, 1.05), 0.05)]
    return dict(name="C_Disc_D3.0mm_W1.6mm_P2.50mm", descr="KiCad stock footprint (Capacitor_THT), ceramic disc",
                attr="through_hole", pads=pads, graphics=g, texts=[("${REFERENCE}", 1.25, 0, "F.Fab", 0.6)],
                ref=(1.25, -2.05, "F.SilkS"), models=[("C_Disc_D3.0mm_W1.6mm_P2.50mm.wrl", (0, 0, 0), (0, 0, 0))],
                bodies=None, wrl_bbox="C_Disc_D3.0mm_W1.6mm_P2.50mm.wrl")

def cp_fp():  # radial electrolytic laid flat on the board, body toward -y
    pads = [("1", "thru_hole", "rect", 0, 0, 1.6, 0.8, "", "passive"),
            ("2", "thru_hole", "circle", 0, 2.5, 1.6, 0.8, "", "passive")]
    g = [("rect", "F.SilkS", (-2.7, -8.2, 2.7, -1.2), 0.12),
         ("rect", "F.Fab", (-2.5, -8.2, 2.5, -1.2), 0.1),
         ("line", "F.SilkS", (-2.1, -0.55, -1.3, -0.55), 0.12), ("line", "F.SilkS", (-1.7, -0.95, -1.7, -0.15), 0.12),
         ("rect", "F.CrtYd", (-2.95, -8.45, 2.95, 3.55), 0.05)]
    b = [("C2 body (5 x 7 mm, laid flat)", -2.5, -8.2, 0, 2.5, -1.2, 5.0),
         ("C2 leads", -0.4, -1.2, -1.6, 0.4, 2.9, 2.6)]
    return dict(name="CP_Radial_D5.0mm_P2.50mm_LaidFlat_L7mm", descr="5 mm radial electrolytic, max 7 mm long, bent over to lie flat (body toward the AHT10)",
                attr="through_hole", pads=pads, graphics=g, texts=[("C2", 0, -4.7, "F.SilkS", 1.0), ("${REFERENCE}", 0, -6.5, "F.Fab", 0.8)],
                ref=(0, -9.2, "F.Fab"), models=[("cp_d5_l7_laidflat.wrl", (0, 0, 0), (0, 0, 0))], bodies=b)

def hole_fp():  # KiCad stock MountingHole:MountingHole_2.2mm_M2
    return dict(name="MountingHole_2.2mm_M2", descr="Mounting hole 2.2 mm (M2), no copper. The case pins go through these",
                attr="exclude_from_pos_files exclude_from_bom",
                pads=[("", "np_thru_hole", "circle", 0, 0, 2.2, 2.2, "", "")],
                graphics=[("circle", "Cmts.User", (0, 0, 2.2), 0.15), ("circle", "F.CrtYd", (0, 0, 2.45), 0.05)],
                texts=[("${REFERENCE}", 0, 0, "F.Fab", 0.8)], ref=(0, -3.2, "F.Fab"), ref_hide=True, models=[], bodies=[])

def case_fp(X0, Y0, Wc, Lc):
    return dict(name="ESP-Soil_Stake_Case_v2", descr="3D-only: the snap-fit stake case (back shell + lid) from hardware/case. Origin = PCB top-left corner",
                attr="board_only exclude_from_pos_files exclude_from_bom",
                pads=[], graphics=[("rect", "F.Fab", (-X0, -Y0, Wc - X0, Lc - Y0), 0.1)],
                texts=[("CASE OUTLINE", Wc/2 - X0, Lc - Y0 - 2.5, "F.Fab", 1.0)], ref=(-X0 + 3, -Y0 - 1.5, "F.Fab"), ref_hide=True,
                models=[("case_back.wrl", (0, 0, 0), (0, 0, 0)), ("case_lid.wrl", (0, 0, 0), (0, 0, 0))], bodies=[])

# ===================================================================== case geometry (from the case generator)
case = {"__file__": os.path.abspath(CASE_SRC)}
_src = open(CASE_SRC).read()          # geometry + voxel() only, not the file-writing part
exec(_src.split("vb,zb=voxel")[0], case)
X0c, Y0c, Ztc = case["X0"], case["Y0"], case["Zt"]
for fn in (xiao_fp, aht_fp, probe_fp, r_fp, c_fp, cp_fp, hole_fp):
    d = fn(); FP[d["name"]] = d
d = case_fp(X0c, Y0c, case["W"], case["L"]); FP[d["name"]] = d

# ===================================================================== parts
# ref, footprint, value, symbol, (x, y) PCB coords from top-left, rotation, pad->net, extra fields
PARTS = [
    ("U1", "XIAO_ESP32C3_THT", "XIAO ESP32-C3", "XIAO_ESP32C3", (12.0, 10.5), 0,
     {"2": "/ADC", "5": "/SDA", "6": "/SCL", "12": "+3V3", "13": "GND"}),
    ("J1", "AHT10_Module_1x04_P2.54mm", "AHT10 module", "AHT10_Module", (12.0, 26.0), 0,
     {"1": "+3V3", "2": "GND", "3": "/SCL", "4": "/SDA"}),
    ("P1", "SEN0193_Wire_Pads_1x03_P2.54mm", "DFRobot SEN0193", "SEN0193", (12.0, 49.5), 0,
     {"1": "/PROBE_A", "2": "+3V3", "3": "GND"}),
    ("R1", "R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical", "10k", "R", (9.46, 46.5), 90, {"1": "/PROBE_A", "2": "/ADC"}),
    ("R2", "R_Axial_DIN0204_L3.6mm_D1.6mm_P2.54mm_Vertical", "33k", "R", (7.0, 43.96), 270, {"1": "/ADC", "2": "GND"}),
    ("C1", "C_Disc_D3.0mm_W1.6mm_P2.50mm", "100n", "C", (4.5, 43.96), 270, {"1": "/ADC", "2": "GND"}),
    ("C2", "CP_Radial_D5.0mm_P2.50mm_LaidFlat_L7mm", "100u 6.3V", "C_Polarized", (19.5, 46.5), 0, {"1": "+3V3", "2": "GND"}),
    ("H1", "MountingHole_2.2mm_M2", "MountingHole", "MountingHole", (5.0, 39.5), 0, {}),
    ("H2", "MountingHole_2.2mm_M2", "MountingHole", "MountingHole", (13.0, 39.5), 0, {}),
    ("CASE1", "ESP-Soil_Stake_Case_v2", "Snap-fit case v2", "Case", (0.0, 0.0), 0, {}),
]
REF_POS = {"R1": (9.46, 42.05), "R2": (7.0, 42.05), "C1": (4.5, 42.05), "P1": (5.6, 50.4), "J1": (19.0, 23.1), "U1": (12.0, 17.0)}

# copper tracks (same routing as v1): net, width, points (PCB coords)
TRACKS = [
    ("/ADC", 0.4, [(4.38, 5.42), (1.8, 5.42), (1.8, 43.96), (4.5, 43.96), (7.0, 43.96), (9.46, 43.96)]),
    ("/SDA", 0.4, [(4.38, 13.04), (15.81, 13.04), (15.81, 26.0)]),
    ("/SCL", 0.4, [(4.38, 15.58), (13.27, 15.58), (13.27, 26.0)]),
    ("+3V3", 0.6, [(19.62, 7.96), (22.3, 7.96), (22.3, 29.0), (8.19, 29.0), (8.19, 26.0)]),
    ("+3V3", 0.6, [(22.3, 29.0), (22.3, 46.5), (19.5, 46.5), (12.0, 46.5), (12.0, 49.5)]),
    ("/PROBE_A", 0.4, [(9.46, 46.5), (9.46, 49.5)]),
]
BOARD_TEXT = [("ESP-SOIL STAKE v" + REV, 12.0, 30.0, 1.1, "B.SilkS"), ("github.com/Gunz0Blazin/esp-soil", 12.0, 32.2, 0.8, "B.SilkS"),
              ("v" + REV, 21.6, 36.6, 0.8, "F.SilkS")]

def rot(lx, ly, a):
    r = math.radians(a); c, s = math.cos(r), math.sin(r)
    return (lx*c + ly*s, -lx*s + ly*c)
def unrot(bx, by, a): return rot(bx, by, -a)

# pad nets including the "unconnected-(...)" names KiCad would assign
def pad_net(ref, fpname, padnum, pinname, nets):
    if padnum in nets: return nets[padnum]
    if FP[fpname]["pads"] and pinname:
        return f"unconnected-({ref}-{pinname}-Pad{padnum})"
    return None

# ===================================================================== s-expression writers (footprint)
def fp_graphic(gr, uid):
    kind, layer, d, w = gr
    st = f'(stroke (width {f(w)}) (type solid))'
    if kind == "line":
        return f'(fp_line (start {f(d[0])} {f(d[1])}) (end {f(d[2])} {f(d[3])}) {st} (layer {q(layer)}) (uuid {q(uid)}))'
    if kind == "rect":
        return f'(fp_rect (start {f(d[0])} {f(d[1])}) (end {f(d[2])} {f(d[3])}) {st} (fill none) (layer {q(layer)}) (uuid {q(uid)}))'
    if kind == "circle":
        return f'(fp_circle (center {f(d[0])} {f(d[1])}) (end {f(d[0] + d[2])} {f(d[1])}) {st} (fill none) (layer {q(layer)}) (uuid {q(uid)}))'

def effects(size, hide=False, justify=None):
    th = round(size*0.15, 3)
    j = f" (justify {justify})" if justify else ""
    return f'(effects (font (size {f(size)} {f(size)}) (thickness {f(th)})){j})'

def footprint_sexpr(d, placed=None):
    """placed = dict(ref, value, x, y, rot, nets, sym_uuid) for the board; None for the library file."""
    a = placed["rot"] if placed else 0
    key = placed["ref"] if placed else d["name"]
    L = []
    if placed:
        L.append(f'(footprint {q(LIB + ":" + d["name"])} (layer "F.Cu") (uuid {q(U("fp", key))}) (at {f(OX + placed["x"])} {f(OY + placed["y"])}{" " + f(a) if a else ""})')
    else:
        L.append(f'(footprint {q(d["name"])} (version 20240108) (generator "pcbnew") (generator_version "8.0") (layer "F.Cu")')
    L.append(f'(descr {q(d["descr"])})')
    ref = placed["ref"] if placed else "REF**"
    val = placed["value"] if placed else d["name"]
    rx, ry, rl = d["ref"]
    if placed and placed["ref"] in REF_POS:          # reference text placed on the board, then made local
        bx, by = REF_POS[placed["ref"]]
        rx, ry = unrot(bx - placed["x"], by - placed["y"], a); rl = "F.SilkS"
    hide_ref = " (hide yes)" if d.get("ref_hide") else ""
    L.append(f'(property "Reference" {q(ref)} (at {f(rx)} {f(ry)} 0) (layer {q(rl)}){hide_ref} (uuid {q(U("ref", key))}) {effects(0.9 if rl == "F.SilkS" else 1.0)})')
    L.append(f'(property "Value" {q(val)} (at 0 0 0) (layer "F.Fab") (hide yes) (uuid {q(U("val", key))}) {effects(1.0)})')
    for p in ("Footprint", "Datasheet", "Description"):
        v = (LIB + ":" + d["name"]) if (p == "Footprint" and placed) else (d["descr"] if p == "Description" else "")
        L.append(f'(property {q(p)} {q(v)} (at 0 0 0) (unlocked yes) (layer "F.Fab") (hide yes) (uuid {q(U(p, key))}) {effects(1.27)})')
    if placed and placed.get("sym_uuid"):
        L.append(f'(path {q("/" + placed["sym_uuid"])}) (sheetname "Root") (sheetfile {q(NAME + ".kicad_sch")})')
    L.append(f'(attr {d["attr"]})')
    for i, gr in enumerate(d["graphics"]):
        L.append(fp_graphic(gr, U("gr", key, i)))
    for i, (txt, x, y, layer, size) in enumerate(d["texts"]):
        L.append(f'(fp_text user {q(txt)} (at {f(x)} {f(y)} 0) (layer {q(layer)}) (uuid {q(U("txt", key, i))}) {effects(size)})')
    for i, (num, kind, shape, x, y, size, drill, pin, ptype) in enumerate(d["pads"]):
        ang = f" {f(a)}" if a else ""
        s = f'(pad {q(num)} {kind} {shape} (at {f(x)} {f(y)}{ang}) (size {f(size)} {f(size)}) (drill {f(drill)}) (layers "*.Cu" "*.Mask")'
        if kind == "thru_hole": s += " (remove_unused_layers no)"
        if placed:
            n = pad_net(placed["ref"], d["name"], num, pin, placed["nets"])
            if n: s += f" (net {net_id(n)} {q(n)})"
            if pin: s += f" (pinfunction {q(pin)})"
            if ptype: s += f" (pintype {q(ptype)})"
        s += f' (uuid {q(U("pad", key, i))}))'
        L.append(s)
    for (fn, off, rt) in d["models"]:
        L.append(f'(model {q("${KIPRJMOD}/3d/" + fn)} (offset (xyz {f(off[0])} {f(off[1])} {f(off[2])})) (scale (xyz 1 1 1)) (rotate (xyz {f(rt[0])} {f(rt[1])} {f(rt[2])})))')
    L.append(")")
    return "\n  ".join(L)

# ===================================================================== symbols
# pins: (number, name, type, x, y, angle, length) in symbol coords (y up)
SYMS = {}
def sym(name, prefix, value, descr, fp, body, pins, power=False, hide_pin_names=False, hide_pin_numbers=False,
        extra_graphics="", ref_at=(0, 0), val_at=(0, 0), in_bom=True, on_board=True, ref_hidden=False, val_hidden=False, ki_fp_filters=""):
    SYMS[name] = dict(prefix=prefix, value=value, descr=descr, fp=fp, body=body, pins=pins, power=power,
                      hide_pin_names=hide_pin_names, hide_pin_numbers=hide_pin_numbers, extra=extra_graphics,
                      ref_at=ref_at, val_at=val_at, in_bom=in_bom, on_board=on_board, ref_hidden=ref_hidden, val_hidden=val_hidden)

xiao_pins = [(str(i+1), f"D{i}", "bidirectional", -12.7, 7.62 - 2.54*i, 0, 2.54) for i in range(7)]
for i, (num, nm) in enumerate([("14", "5V"), ("13", "GND"), ("12", "3V3"), ("11", "D10"), ("10", "D9"), ("9", "D8"), ("8", "D7")]):
    ty = {"5V": "power_in", "GND": "power_in", "3V3": "power_out"}.get(nm, "bidirectional")
    xiao_pins.append((num, nm, ty, 12.7, 7.62 - 2.54*i, 180, 2.54))
sym("XIAO_ESP32C3", "U", "XIAO ESP32-C3", "Seeed Studio XIAO ESP32-C3 (pin map from Seeed's KiCad library)",
    LIB + ":XIAO_ESP32C3_THT", (-10.16, 10.16, 10.16, -10.16), xiao_pins, ref_at=(0, 11.43), val_at=(0, -11.43))
sym("AHT10_Module", "J", "AHT10 module", "AHT10 temperature/humidity breakout, I2C 0x38",
    LIB + ":AHT10_Module_1x04_P2.54mm", (-5.08, 5.08, 5.08, -5.08),
    [("1", "VIN", "power_in", -7.62, 3.81, 0, 2.54), ("2", "GND", "power_in", -7.62, 1.27, 0, 2.54),
     ("3", "SCL", "input", -7.62, -1.27, 0, 2.54), ("4", "SDA", "bidirectional", -7.62, -3.81, 0, 2.54)],
    ref_at=(0, 6.35), val_at=(0, -6.35))
sym("SEN0193", "P", "DFRobot SEN0193", "Capacitive soil moisture probe, leads soldered to the board",
    LIB + ":SEN0193_Wire_Pads_1x03_P2.54mm", (-5.08, 3.81, 5.08, -3.81),
    [("1", "SIG", "output", -7.62, 2.54, 0, 2.54), ("2", "VCC", "power_in", -7.62, 0, 0, 2.54), ("3", "GND", "power_in", -7.62, -2.54, 0, 2.54)],
    ref_at=(0, 5.08), val_at=(0, -5.08))
sym("R", "R", "R", "Resistor", "", (-1.016, 2.54, 1.016, -2.54),
    [("1", "~", "passive", 0, 3.81, 270, 1.27), ("2", "~", "passive", 0, -3.81, 90, 1.27)],
    hide_pin_names=True, hide_pin_numbers=True, ref_at=(2.032, 0.635), val_at=(2.032, -1.905))
sym("C", "C", "C", "Unpolarized capacitor", "", None,
    [("1", "~", "passive", 0, 3.81, 270, 2.794), ("2", "~", "passive", 0, -3.81, 90, 2.794)],
    hide_pin_names=True, hide_pin_numbers=True, ref_at=(2.54, 0.635), val_at=(2.54, -1.905),
    extra_graphics='(polyline (pts (xy -2.032 0.762) (xy 2.032 0.762)) (stroke (width 0.508) (type default)) (fill (type none)))'
                   ' (polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762)) (stroke (width 0.508) (type default)) (fill (type none)))')
sym("C_Polarized", "C", "C_Polarized", "Polarized capacitor", "", None,
    [("1", "~", "passive", 0, 3.81, 270, 2.794), ("2", "~", "passive", 0, -3.81, 90, 2.794)],
    hide_pin_names=True, hide_pin_numbers=True, ref_at=(2.54, 0.635), val_at=(2.54, -1.905),
    extra_graphics='(rectangle (start -2.286 0.508) (end 2.286 1.016) (stroke (width 0) (type default)) (fill (type none)))'
                   ' (polyline (pts (xy -1.778 2.286) (xy -0.762 2.286)) (stroke (width 0) (type default)) (fill (type none)))'
                   ' (polyline (pts (xy -1.27 2.794) (xy -1.27 1.778)) (stroke (width 0) (type default)) (fill (type none)))'
                   ' (rectangle (start 2.286 -1.016) (end -2.286 -0.508) (stroke (width 0) (type default)) (fill (type outline)))')
sym("MountingHole", "H", "MountingHole", "Mounting hole, no connection (case pin goes through)", LIB + ":MountingHole_2.2mm_M2", None, [],
    ref_at=(2.54, 0.635), val_at=(2.54, -1.27), in_bom=False,
    extra_graphics='(circle (center 0 0) (radius 1.27) (stroke (width 1.27) (type default)) (fill (type none)))')
sym("Case", "CASE", "Snap-fit case", "3D-only part that carries the case model for fit checks", LIB + ":ESP-Soil_Stake_Case_v2",
    (-3.81, 2.54, 3.81, -2.54), [], ref_at=(0, 3.81), val_at=(0, -3.81), in_bom=False)
sym("GND", "#PWR", "GND", "Power symbol: GND", "", None, [("1", "GND", "power_in", 0, 0, 270, 0)], power=True,
    hide_pin_names=True, hide_pin_numbers=True, ref_at=(0, -6.35), val_at=(0, -3.81), ref_hidden=True,
    extra_graphics='(polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27)) (stroke (width 0) (type default)) (fill (type none)))')
sym("+3V3", "#PWR", "+3V3", "Power symbol: +3V3", "", None, [("1", "+3V3", "power_in", 0, 0, 90, 0)], power=True,
    hide_pin_names=True, hide_pin_numbers=True, ref_at=(0, -3.81), val_at=(0, 3.556), ref_hidden=True,
    extra_graphics='(polyline (pts (xy -0.762 1.27) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none)))'
                   ' (polyline (pts (xy 0 0) (xy 0 2.54)) (stroke (width 0) (type default)) (fill (type none)))'
                   ' (polyline (pts (xy 0 2.54) (xy 0.762 1.27)) (stroke (width 0) (type default)) (fill (type none)))')
sym("PWR_FLAG", "#FLG", "PWR_FLAG", "Marks a net as driven by a power source", "", None, [("1", "pwr", "power_out", 0, 0, 90, 0)], power=True,
    hide_pin_names=True, hide_pin_numbers=True, ref_at=(0, 1.905), val_at=(0, 3.81), ref_hidden=True,
    extra_graphics='(polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27)) (stroke (width 0) (type default)) (fill (type none)))')

def sch_effects(hide=False, justify=None, size=1.27):
    j = f" (justify {justify})" if justify else ""
    h = " hide" if hide else ""
    return f"(effects (font (size {f(size)} {f(size)})){j}{h})"

def symbol_def(name, d, prefix_lib):
    nm = (LIB + ":" + name) if prefix_lib else name
    L = [f'(symbol {q(nm)}']
    if d["power"]: L.append("(power)")
    if d["hide_pin_numbers"]: L.append("(pin_numbers hide)")
    L.append(f'(pin_names (offset {"0" if d["hide_pin_names"] else "1.016"}){" hide" if d["hide_pin_names"] else ""})')
    L.append(f'(exclude_from_sim no) (in_bom {"yes" if d["in_bom"] else "no"}) (on_board {"yes" if d["on_board"] else "no"})')
    rx, ry = d["ref_at"]; vx, vy = d["val_at"]
    L.append(f'(property "Reference" {q(d["prefix"])} (at {f(rx)} {f(ry)} 0) {sch_effects(d["ref_hidden"])})')
    L.append(f'(property "Value" {q(d["value"])} (at {f(vx)} {f(vy)} 0) {sch_effects(d["val_hidden"])})')
    L.append(f'(property "Footprint" {q(d["fp"])} (at 0 0 0) {sch_effects(True)})')
    L.append(f'(property "Datasheet" "~" (at 0 0 0) {sch_effects(True)})')
    L.append(f'(property "Description" {q(d["descr"])} (at 0 0 0) {sch_effects(True)})')
    g = []
    if d["body"]:
        x0, y0, x1, y1 = d["body"]
        g.append(f'(rectangle (start {f(x0)} {f(y0)}) (end {f(x1)} {f(y1)}) (stroke (width 0.254) (type default)) (fill (type background)))')
    if d["extra"]: g.append(d["extra"])
    L.append(f'(symbol {q(name + "_0_1")} ' + " ".join(g) + ")")
    pins = []
    for num, pn, ty, x, y, ang, ln in d["pins"]:
        hide = " hide" if d["power"] else ""
        pins.append(f'(pin {ty} line (at {f(x)} {f(y)} {ang}) (length {f(ln)}){hide} (name {q(pn)} {sch_effects()}) (number {q(num)} {sch_effects()}))')
    L.append(f'(symbol {q(name + "_1_1")} ' + " ".join(pins) + ")")
    L.append(")")
    return "\n    ".join(L)

# ===================================================================== schematic
sch_items, sch_syms, SCH_NET_SPEC = [], [], []
pwr_count = [0]

def place_symbol(ref, lib, value, x, y, fields=None, hidden_ref=False):
    d = SYMS[lib]; uid = U("sym", ref)
    rx, ry = d["ref_at"]; vx, vy = d["val_at"]
    fp = d["fp"]
    if ref in PART_BY_REF: fp = LIB + ":" + PART_BY_REF[ref][1]
    L = [f'(symbol (lib_id {q(LIB + ":" + lib)}) (at {f(x)} {f(y)} 0) (unit 1) (exclude_from_sim no) (in_bom {"yes" if d["in_bom"] else "no"}) (on_board {"yes" if d["on_board"] else "no"}) (dnp no) (uuid {q(uid)})',
         f'(property "Reference" {q(ref)} (at {f(x + rx)} {f(y - ry)} 0) {sch_effects(d["ref_hidden"] or hidden_ref)})',
         f'(property "Value" {q(value)} (at {f(x + vx)} {f(y - vy)} 0) {sch_effects(d["val_hidden"])})',
         f'(property "Footprint" {q(fp)} (at {f(x)} {f(y)} 0) {sch_effects(True)})',
         f'(property "Datasheet" "~" (at {f(x)} {f(y)} 0) {sch_effects(True)})',
         f'(property "Description" {q(d["descr"])} (at {f(x)} {f(y)} 0) {sch_effects(True)})']
    for k, v in (fields or {}).items():
        L.append(f'(property {q(k)} {q(v)} (at {f(x)} {f(y)} 0) {sch_effects(True)})')
    for num, *_ in d["pins"]:
        L.append(f'(pin {q(num)} (uuid {q(U("sympin", ref, num))}))')
    L.append(f'(instances (project {q(NAME)} (path {q("/" + ROOT)} (reference {q(ref)}) (unit 1))))')
    L.append(")")
    sch_syms.append("\n    ".join(L))
    return uid

def pin_end(lib, num, x, y):
    for p in SYMS[lib]["pins"]:
        if p[0] == num: return (x + p[3], y - p[4], p[5])
    raise KeyError(num)

OUTWARD = {0: (-1, 0), 180: (1, 0), 270: (0, -1), 90: (0, 1)}   # sheet direction away from the body
def wire(a, b, key):
    sch_items.append(f'(wire (pts (xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])})) (stroke (width 0) (type default)) (uuid {q(U("wire", key))}))')

def power_sym(kind, x, y, key):
    pwr_count[0] += 1
    prefix = "#FLG" if kind == "PWR_FLAG" else "#PWR"
    ref = f"{prefix}{pwr_count[0]:02d}"
    place_symbol(ref, kind, kind, x, y)

def connect(ref, lib, sx, sy, num, how):
    px, py, ang = pin_end(lib, num, sx, sy)
    dx, dy = OUTWARD[ang]
    key = f"{ref}.{num}"
    if how == "nc":
        sch_items.append(f'(no_connect (at {f(px)} {f(py)}) (uuid {q(U("nc", key))}))')
        SCH_NET_SPEC.append((ref, num, None)); return
    ex, ey = px + dx*2.54, py + dy*2.54
    wire((px, py), (ex, ey), key)
    if how in ("GND", "+3V3"):
        power_sym(how, ex, ey, key)
        SCH_NET_SPEC.append((ref, num, how))
    else:
        ang_l = {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        just = "left bottom" if ang_l in (0, 90) else "right bottom"
        sch_items.append(f'(label {q(how)} (at {f(ex)} {f(ey)} {ang_l}) (fields_autoplaced yes) {sch_effects(justify=just)} (uuid {q(U("label", key))}))')
        SCH_NET_SPEC.append((ref, num, "/" + how))

def note(text, x, y, size=1.27):
    sch_items.append(f'(text {q(text)} (exclude_from_sim no) (at {f(x)} {f(y)} 0) {sch_effects(justify="left bottom", size=size)} (uuid {q(U("text", text[:30]))}))')

PART_BY_REF = {p[0]: p for p in PARTS}

def build_schematic():
    G = 2.54
    # XIAO
    ux, uy = 30*G, 35*G
    place_symbol("U1", "XIAO_ESP32C3", "XIAO ESP32-C3", ux, uy)
    xiao_conn = {"1": "nc", "2": "ADC", "3": "nc", "4": "nc", "5": "SDA", "6": "SCL", "7": "nc",
                 "8": "nc", "9": "nc", "10": "nc", "11": "nc", "12": "+3V3", "13": "GND", "14": "nc"}
    for n, how in xiao_conn.items(): connect("U1", "XIAO_ESP32C3", ux, uy, n, how)
    note("XIAO ESP32-C3 (powered by USB-C)\nD1/GPIO3 = probe ADC, D4/GPIO6 = SDA, D5/GPIO7 = SCL\nIts 3V3 pin powers the probe and the AHT10.\nThe C3 has no onboard antenna: plug the\nincluded FPC antenna into the U.FL jack.", 18*G, 45*G)
    # AHT10
    jx, jy = 64*G, 27*G
    place_symbol("J1", "AHT10_Module", "AHT10 module", jx, jy)
    for n, how in {"1": "+3V3", "2": "GND", "3": "SCL", "4": "SDA"}.items(): connect("J1", "AHT10_Module", jx, jy, n, how)
    note("AHT10 breakout on a 4-pin header (V G C D).\nOwn pull-ups on the module.", 58*G, 34*G)
    # probe + divider
    px_, py_ = 92*G, 55*G
    place_symbol("P1", "SEN0193", "DFRobot SEN0193", px_, py_)
    for n, how in {"1": "PROBE_A", "2": "+3V3", "3": "GND"}.items(): connect("P1", "SEN0193", px_, py_, n, how)
    for ref, lib, val, x, y, conns in [
        ("R1", "R", "10k", 60*G, 55*G, {"1": "PROBE_A", "2": "ADC"}),
        ("R2", "R", "33k", 68*G, 55*G, {"1": "ADC", "2": "GND"}),
        ("C1", "C", "100n", 76*G, 55*G, {"1": "ADC", "2": "GND"}),
        ("C2", "C_Polarized", "100u 6.3V", 50*G, 27*G, {"1": "+3V3", "2": "GND"}),
    ]:
        place_symbol(ref, lib, val, x, y)
        for n, how in conns.items(): connect(ref, lib, x, y, n, how)
    note("Probe output is ~2.5 V dry / ~1.2 V wet. The C3's ADC tops out near 2.5 V,\nso R1/R2 scale it by 33k/(10k+33k) = 0.767. C1 filters ADC noise.\nCalibrate dry_v / wet_v at the ESP pin (after the divider).", 58*G, 64*G)
    note("C2: bulk cap for Wi-Fi current spikes, laid flat.", 44*G, 35*G)
    # power flag
    place_symbol("#FLG01", "PWR_FLAG", "PWR_FLAG", 20*G, 62*G); pwr_count[0] = max(pwr_count[0], 1)
    place_symbol("#PWR99", "GND", "GND", 20*G, 62*G)
    SCH_NET_SPEC.append(("#FLG01", "1", "GND"))
    # mechanical
    place_symbol("H1", "MountingHole", "MountingHole", 20*G, 72*G)
    place_symbol("H2", "MountingHole", "MountingHole", 26*G, 72*G)
    place_symbol("CASE1", "Case", "Snap-fit case v2", 36*G, 72*G)
    note("Mechanical: H1/H2 take the case's locating pins. CASE1 only carries the\ncase 3D model so the 3D viewer shows the board inside the case.", 18*G, 77*G)
    note("ESP-Soil stake v" + REV + "  github.com/Gunz0Blazin/esp-soil", 18*G, 12*G, 2.0)

def schematic_text():
    build_schematic()
    used = sorted({s.split('lib_id "')[1].split('"')[0].split(":")[1] for s in sch_syms})
    libs = "\n    ".join(symbol_def(n, SYMS[n], True) for n in used)
    head = (f'(kicad_sch (version 20231120) (generator "eeschema") (generator_version "8.0") (uuid {q(ROOT)}) (paper "A4")\n'
            f'  (title_block (title "ESP-Soil stake") (date {q(DATE)}) (rev {q(REV)}) (company "github.com/Gunz0Blazin/esp-soil")'
            f' (comment 1 "XIAO ESP32-C3 + SEN0193 soil probe + AHT10, one stake per pot"))\n')
    return (head + "  (lib_symbols\n    " + libs + "\n  )\n  " + "\n  ".join(sch_items) + "\n  " +
            "\n  ".join(sch_syms) + '\n  (sheet_instances (path "/" (page "1")))\n)\n')

# ===================================================================== board
def board_text():
    sym_uuid = {p[0]: U("sym", p[0]) for p in PARTS}
    fps = []
    for ref, fpn, val, _s, (x, y), a, nets in PARTS:
        fps.append(footprint_sexpr(FP[fpn], dict(ref=ref, value=val, x=x, y=y, rot=a, nets=nets, sym_uuid=sym_uuid[ref])))
    segs = []
    for ti, (net, w, pts) in enumerate(TRACKS):
        for i in range(len(pts) - 1):
            (x1, y1), (x2, y2) = pts[i], pts[i+1]
            segs.append(f'(segment (start {f(OX+x1)} {f(OY+y1)}) (end {f(OX+x2)} {f(OY+y2)}) (width {f(w)}) (layer "F.Cu") (net {net_id(net)}) (uuid {q(U("seg", ti, i))}))')
    m = 0.5
    zone = (f'(zone (net {net_id("GND")}) (net_name "GND") (layer "B.Cu") (uuid {q(U("zone"))}) (name "GND pour") (hatch edge 0.5)'
            f' (connect_pads (clearance 0.3)) (min_thickness 0.25) (filled_areas_thickness no)'
            f' (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))'
            f' (polygon (pts (xy {f(OX+m)} {f(OY+m)}) (xy {f(OX+W-m)} {f(OY+m)}) (xy {f(OX+W-m)} {f(OY+H-m)}) (xy {f(OX+m)} {f(OY+H-m)}))))')
    gr = [f'(gr_rect (start {f(OX)} {f(OY)}) (end {f(OX+W)} {f(OY+H)}) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid {q(U("edge"))}))']
    for i, (t, x, y, s, layer) in enumerate(BOARD_TEXT):
        gr.append(f'(gr_text {q(t)} (at {f(OX+x)} {f(OY+y)} 0) (layer {q(layer)}) (uuid {q(U("grtext", i))}) '
                  f'{effects(s, justify="mirror" if layer.startswith("B.") else None)})')
    nets = "\n  ".join(f'(net {i} {q(n)})' for i, n in enumerate(NETS))
    layers = ('(layers (0 "F.Cu" signal) (31 "B.Cu" signal) (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive")'
              ' (34 "B.Paste" user) (35 "F.Paste" user) (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")'
              ' (38 "B.Mask" user) (39 "F.Mask" user) (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments")'
              ' (42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2") (44 "Edge.Cuts" user) (45 "Margin" user)'
              ' (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") (48 "B.Fab" user) (49 "F.Fab" user))')
    body = "\n  ".join(fps + segs + [zone] + gr)
    return (f'(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")\n'
            f'  (general (thickness 1.6) (legacy_teardrops no))\n  (paper "A4")\n'
            f'  (title_block (title "ESP-Soil stake") (date {q(DATE)}) (rev {q(REV)}) (company "github.com/Gunz0Blazin/esp-soil"))\n'
            f'  {layers}\n  (setup (pad_to_mask_clearance 0) (allow_soldermask_bridges_in_footprints no))\n  {nets}\n  {body}\n)\n')

# ===================================================================== project + lib tables
def project_json():
    rules = {"min_clearance": 0.2, "min_track_width": 0.2, "min_via_annular_width": 0.1, "min_via_diameter": 0.45,
             "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.5, "min_hole_clearance": 0.25,
             "min_copper_edge_clearance": 0.3, "min_silk_clearance": 0.0, "min_text_height": 0.8, "min_text_thickness": 0.08,
             "solder_mask_to_copper_clearance": 0.0, "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1,
             "max_error": 0.005, "allow_blind_buried_vias": False, "allow_microvias": False, "use_height_for_length_calcs": True}
    nc = lambda name, w: {"name": name, "clearance": 0.2, "track_width": w, "via_diameter": 0.6, "via_drill": 0.3,
                          "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "line_style": 0,
                          "microvia_diameter": 0.3, "microvia_drill": 0.1, "pcb_color": "rgba(0, 0, 0, 0.000)",
                          "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6, "bus_width": 12, "priority": 2147483647 if name == "Default" else 0}
    return {
        "board": {"design_settings": {"defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "silk_line_width": 0.12,
                                                     "silk_text_size_h": 1.0, "silk_text_size_v": 1.0, "silk_text_thickness": 0.15},
                                        "rules": rules,
                                        "rule_severities": {"lib_footprint_mismatch": "ignore", "lib_footprint_issues": "warning"}},
                  "3dviewer": {}},
        "boards": [], "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": NAME + ".kicad_pro", "version": 1},
        "net_settings": {"classes": [nc("Default", 0.4), nc("Power", 0.6)], "meta": {"version": 3},
                         "net_colors": None, "netclass_assignments": None,
                         "netclass_patterns": [{"netclass": "Power", "pattern": "+3V3"}, {"netclass": "Power", "pattern": "GND"}]},
        "pcbnew": {"last_paths": {"gencad": "", "idf": "", "netlist": "", "plot": "gerbers/", "pos_files": "", "specctra_dsn": "", "step": "", "svg": "", "vrml": ""}, "page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[ROOT, "Root"]],
        "text_variables": {}}

# ===================================================================== 3D models (VRML 2, 1 unit = 0.1 in)
def box_mesh(x0, y0, z0, x1, y1, z1):
    V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    F = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return np.array(V, float), np.array(F, int)
def cyl_y_mesh(cx, cz, r, y0, y1, n=24):
    V, F = [], []
    for i in range(n):
        a = 2*math.pi*i/n; V += [(cx + r*math.cos(a), y0, cz + r*math.sin(a)), (cx + r*math.cos(a), y1, cz + r*math.sin(a))]
    V += [(cx, y0, cz), (cx, y1, cz)]
    for i in range(n):
        j = (i + 1) % n
        F += [(2*i, 2*j, 2*j+1), (2*i, 2*j+1, 2*i+1), (2*n, 2*j, 2*i), (2*n+1, 2*i+1, 2*j+1)]
    return np.array(V, float), np.array(F, int)
def cyl_z_mesh(cx, cy, r, z0, z1, n=24):
    V, F = cyl_y_mesh(0, 0, r, z0, z1, n)
    V = np.c_[V[:, 0] + cx, V[:, 2] + cy, V[:, 1]]
    return V, F[:, ::-1]

def wrl(fn, shapes):
    """shapes: list of (verts mm in footprint frame (x right, y down, z up), faces, rgb, transparency)"""
    out = ["#VRML V2.0 utf8", "# ESP-Soil stake model, generated by gen_kicad.py. Units: 0.1 in (KiCad VRML convention)"]
    for V, F, rgb, tr in shapes:
        P = np.c_[V[:, 0], -V[:, 1], V[:, 2]] / 2.54
        pts = ",".join(f"{a:.4f} {b:.4f} {c:.4f}" for a, b, c in P)
        idx = ",".join(f"{a},{b},{c},-1" for a, b, c in F)
        out.append("Shape { appearance Appearance { material Material { diffuseColor %.3f %.3f %.3f specularColor 0.2 0.2 0.2 "
                   "shininess 0.2 transparency %.2f } } geometry IndexedFaceSet { solid FALSE creaseAngle 0.6 "
                   "coord Coordinate { point [ %s ] } coordIndex [ %s ] } }" % (*rgb, tr, pts, idx))
    open(os.path.join(PROJ, "3d", fn), "w").write("\n".join(out) + "\n")

BLACK, GOLD, PCBBLUE, PCBGREEN, SILVER, WHITE, PURPLE, CAP = (0.1, 0.1, 0.1), (0.85, 0.7, 0.3), (0.1, 0.25, 0.6), (0.05, 0.35, 0.15), (0.75, 0.75, 0.78), (0.9, 0.9, 0.9), (0.35, 0.15, 0.45), (0.15, 0.2, 0.55)

def body_meshes(bodies, colors):
    return [(*box_mesh(*b[1:]), colors.get(b[0].split(" (")[0], (0.5, 0.5, 0.5)), 0.0) for b in bodies]

def write_models():
    xb = FP["XIAO_ESP32C3_THT"]["bodies"]
    sh = body_meshes(xb, {"header plastic L": BLACK, "header plastic R": BLACK, "XIAO PCB": PURPLE,
                          "XIAO USB-C receptacle": SILVER, "XIAO parts": (0.2, 0.2, 0.22), "XIAO U.FL antenna jack": GOLD})
    sh = [s for s, b in zip(sh, xb) if "pins" not in b[0]]
    for i in range(14):                                   # individual header pins
        x, y = (-7.62, -7.62 + 2.54*i) if i < 7 else (7.62, -7.62 + 2.54*(i-7))
        sh.append((*box_mesh(x-0.32, y-0.32, -3.1, x+0.32, y+0.32, 5.5), GOLD, 0.0))
    wrl("xiao_esp32c3.wrl", sh)
    ab = FP["AHT10_Module_1x04_P2.54mm"]["bodies"]
    sh = [(*box_mesh(*b[1:]), {"header plastic": BLACK, "AHT10 module PCB": PCBBLUE, "AHT10 sensor": WHITE}.get(b[0].split(" (")[0], BLACK), 0.0)
          for b in ab if "pins" not in b[0]]
    for i in range(4):
        x = -3.81 + 2.54*i; sh.append((*box_mesh(x-0.32, -0.32, -3.1, x+0.32, 0.32, 4.6), GOLD, 0.0))
    wrl("aht10_module.wrl", sh)
    pb = FP["SEN0193_Wire_Pads_1x03_P2.54mm"]["bodies"]
    sh = [(*box_mesh(*pb[1][1:]), BLACK, 0.0), (*box_mesh(*pb[2][1:]), (0.25, 0.25, 0.25), 0.0),
          (*box_mesh(-11.5, 60.0, 0.0, 11.5, 60.4, 0.02), WHITE, 0.0)]        # warning-line marker
    for x, c in [(-2.54, (0.2, 0.3, 0.9)), (0, (0.9, 0.15, 0.15)), (2.54, BLACK)]:
        sh.append((*box_mesh(x-0.4, 0, 0, x+0.4, 6.5, 0.6), c, 0.0))
    wrl("sen0193_probe.wrl", sh)
    sh = [(*cyl_y_mesh(0, 2.5, 2.5, -8.2, -1.2), CAP, 0.0), (*box_mesh(-0.25, -1.2, 0, 0.25, 0.25, 2.6), SILVER, 0.0),
          (*box_mesh(-0.25, -0.25, -1.6, 0.25, 0.25, 0), SILVER, 0.0), (*box_mesh(-0.25, 2.25, -1.6, 0.25, 2.75, 1.5), SILVER, 0.0),
          (*box_mesh(-0.25, -1.2, 1.25, 0.25, 2.75, 1.75), SILVER, 0.0)]
    wrl("cp_d5_l7_laidflat.wrl", sh)
    # case: same CSG as hardware/case, meshed at 0.4 mm for a light file; frame = PCB top-left, z from PCB top
    from skimage.measure import marching_cubes
    case["res"] = 0.4
    out = []
    for ops, zlo, zhi, rgb, tr in [(case["back_ops"], 0, case["Hs"], (0.2, 0.55, 0.3), 0.15),
                                   (case["lid_ops"], case["Zt"] - 0.2, case["Hs"] + case["lid_t"], (0.85, 0.85, 0.8), 0.55)]:
        v, z0 = case["voxel"](ops, zlo, zhi)
        V, F, _, _ = marching_cubes(np.pad(v, 1).astype(np.float32), 0.5, spacing=(0.4, 0.4, 0.4))
        V -= 0.4; V[:, 2] += z0
        V = np.c_[V[:, 0] - X0c, V[:, 1] - Y0c, V[:, 2] - Ztc]
        out.append((V, F, rgb, tr))
    wrl("case_back.wrl", [out[0]]); wrl("case_lid.wrl", [out[1]])

def wrl_bbox(fn):
    s = open(os.path.join(PROJ, "3d", fn)).read()
    P = np.vstack([np.array(b.replace(",", " ").split(), float).reshape(-1, 3) for b in re.findall(r"point\s*\[([^\]]*)\]", s)]) * 2.54
    return (float(P[:, 0].min()), float(-P[:, 1].max()), float(P[:, 2].min()), float(P[:, 0].max()), float(-P[:, 1].min()), float(P[:, 2].max()))

def bodies_json():
    out = []
    for ref, fpn, val, _s, (x, y), a, nets in PARTS:
        d = FP[fpn]
        bl = d["bodies"] if d.get("bodies") is not None else [(f"{ref} body+leads (KiCad model bbox)", *wrl_bbox(d["wrl_bbox"]))]
        for b in bl:
            lx0, ly0, z0, lx1, ly1, z1 = b[1:]
            cs = [rot(px, py, a) for px in (lx0, lx1) for py in (ly0, ly1)]
            xs = [x + c[0] for c in cs]; ys = [y + c[1] for c in cs]
            out.append(dict(ref=ref, part=b[0], box=[min(xs), min(ys), z0, max(xs), max(ys), z1]))
    json.dump(out, open(os.path.join(PROJ, "3d", "bodies.json"), "w"), indent=1)

# ===================================================================== write everything
def main():
    pretty = os.path.join(PROJ, LIB + ".pretty"); os.makedirs(pretty, exist_ok=True)
    for n, d in FP.items():
        open(os.path.join(pretty, n + ".kicad_mod"), "w").write(footprint_sexpr(d) + "\n")
    open(os.path.join(PROJ, LIB + ".kicad_sym"), "w").write(
        '(kicad_symbol_lib (version 20231120) (generator "kicad_symbol_editor") (generator_version "8.0")\n  ' +
        "\n  ".join(symbol_def(n, d, False) for n, d in SYMS.items()) + "\n)\n")
    open(os.path.join(PROJ, NAME + ".kicad_sch"), "w").write(schematic_text())
    open(os.path.join(PROJ, NAME + ".kicad_pcb"), "w").write(board_text())
    json.dump(project_json(), open(os.path.join(PROJ, NAME + ".kicad_pro"), "w"), indent=2)
    open(os.path.join(PROJ, "fp-lib-table"), "w").write(
        f'(fp_lib_table\n  (version 7)\n  (lib (name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/{LIB}.pretty")(options "")(descr "ESP-Soil stake parts"))\n)\n')
    open(os.path.join(PROJ, "sym-lib-table"), "w").write(
        f'(sym_lib_table\n  (version 7)\n  (lib (name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/{LIB}.kicad_sym")(options "")(descr "ESP-Soil stake parts"))\n)\n')
    write_models()
    bodies_json()
    print("wrote", NAME, "| nets:", len(NETS) - 1, "| footprints:", len(PARTS), "| symbols in lib:", len(SYMS))

if __name__ == "__main__":
    main()
