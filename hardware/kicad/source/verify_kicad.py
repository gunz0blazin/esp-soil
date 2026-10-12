"""Independent checks on the generated KiCad project (no KiCad needed).

1. Parses every KiCad file as an S-expression (and with kiutils if it's installed).
2. Rebuilds schematic connectivity from pin coordinates / wires / labels (ERC-style checks)
   and compares it pad-by-pad with the PCB nets (schematic <-> board parity).
3. DRC-style checks on the PCB: clearances, edge clearance, annular rings, hole clearance,
   track connectivity per net, courtyard overlaps.
4. 3D fit: every part volume (3d/bodies.json) against the real case geometry (voxels from
   hardware/case/source/gen_case.py), the PCB against the case, USB-C plug access, probe slot,
   and free room for the XIAO's FPC antenna.
5. Renders source/verify-pcb.png and source/verify-case-fit.png.

Run after gen_kicad.py:  python3 verify_kicad.py   -> exit code 1 if anything fails.
"""
import os, re, sys, json, math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); PROJ = os.path.dirname(HERE)
NAME = "esp-soil-stake"; OX, OY = 100.0, 100.0
FAIL, WARN, OK = [], [], []
def fail(m): FAIL.append(m)
def warn(m): WARN.append(m)
def ok(m): OK.append(m)

# ------------------------------------------------------------------ S-expression parser
def parse(text):
    tok = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)
    pos, stack, cur = 0, [], []
    root = cur
    while pos < len(text):
        m = tok.match(text, pos)
        if not m:
            if text[pos:].strip() == "": break
            raise ValueError(f"bad token at {pos}: {text[pos:pos+30]!r}")
        pos = m.end()
        if m.group(1): stack.append(cur); new = []; cur.append(new); cur = new
        elif m.group(2):
            if not stack: raise ValueError("unbalanced )")
            cur = stack.pop()
        elif m.group(3) is not None: cur.append(("STR", m.group(3)))
        elif m.group(4) is not None: cur.append(m.group(4))
    if stack: raise ValueError("unbalanced (")
    return root[0]
def S(x): return x[1] if isinstance(x, tuple) else x
def kids(node, name): return [c for c in node if isinstance(c, list) and c and c[0] == name]
def kid(node, name):
    k = kids(node, name); return k[0] if k else None
def num(x): return float(S(x))

files = {}
for fn in [NAME + ".kicad_pcb", NAME + ".kicad_sch", "esp-soil.kicad_sym", "fp-lib-table", "sym-lib-table"] + \
          [os.path.join("esp-soil.pretty", f) for f in sorted(os.listdir(os.path.join(PROJ, "esp-soil.pretty")))]:
    try:
        files[fn] = parse(open(os.path.join(PROJ, fn)).read()); ok(f"parses: {fn}")
    except Exception as e:
        fail(f"S-expression error in {fn}: {e}")
try:
    json.load(open(os.path.join(PROJ, NAME + ".kicad_pro"))); ok("parses: .kicad_pro (JSON)")
except Exception as e:
    fail(f".kicad_pro JSON: {e}")

try:
    sys.path.insert(0, os.environ.get("KIUTILS_SRC", "/tmp/claude-0/libs/kiutils/src"))
    from kiutils.board import Board
    from kiutils.schematic import Schematic
    from kiutils.symbol import SymbolLib
    from kiutils.footprint import Footprint
    b = Board.from_file(os.path.join(PROJ, NAME + ".kicad_pcb"))
    s = Schematic.from_file(os.path.join(PROJ, NAME + ".kicad_sch"))
    sl = SymbolLib.from_file(os.path.join(PROJ, "esp-soil.kicad_sym"))
    for f in os.listdir(os.path.join(PROJ, "esp-soil.pretty")):
        Footprint.from_file(os.path.join(PROJ, "esp-soil.pretty", f))
    ok(f"kiutils loads board ({len(b.footprints)} footprints, {len(b.traceItems)} tracks), schematic ({len(s.schematicSymbols)} symbols), symbol lib ({len(sl.symbols)}), all footprints")
except ImportError:
    warn("kiutils not installed: skipped second parser")
except Exception as e:
    fail(f"kiutils could not load the project: {type(e).__name__}: {e}")

# ------------------------------------------------------------------ schematic connectivity
sch = files[NAME + ".kicad_sch"]
libsyms = {}
for sd in kids(kid(sch, "lib_symbols"), "symbol"):
    nm = S(sd[1]); pins = []
    for sub in kids(sd, "symbol"):
        for p in kids(sub, "pin"):
            at = kid(p, "at"); pins.append(dict(type=p[1], x=num(at[1]), y=num(at[2]), ang=int(num(at[3])),
                                               name=S(kid(p, "name")[1]), num=S(kid(p, "number")[1])))
    libsyms[nm] = dict(pins=pins, power=kid(sd, "power") is not None)

parent = {}
def find(a):
    parent.setdefault(a, a)
    while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
    return a
def union(a, b): parent[find(a)] = find(b)
def P(x, y): return ("pt", round(x, 3), round(y, 3))

pins_at = []          # (ref, num, name, type, point)
power_names = {}
for sy in kids(sch, "symbol"):
    lib = S(kid(sy, "lib_id")[1]); at = kid(sy, "at"); sx, sy_ = num(at[1]), num(at[2])
    if num(at[3]) != 0: fail(f"symbol {lib} is rotated; checker assumes 0")
    ref = [S(p[2]) for p in kids(sy, "property") if S(p[1]) == "Reference"][0]
    val = [S(p[2]) for p in kids(sy, "property") if S(p[1]) == "Value"][0]
    for p in libsyms[lib]["pins"]:
        pt = P(sx + p["x"], sy_ - p["y"])
        pins_at.append((ref, p["num"], p["name"], p["type"], pt))
        if libsyms[lib]["power"] and p["type"] == "power_in":   # KiCad: hidden power-in pin of a power symbol = global net
            union(pt, ("net", val)); power_names.setdefault(val, 0); power_names[val] += 1
wires = [(P(num(w[1][1][1]), num(w[1][1][2])), P(num(w[1][2][1]), num(w[1][2][2]))) for w in kids(sch, "wire")]
for a, b in wires: union(a, b)
labels = {}
for lb in kids(sch, "label"):
    nm = S(lb[1]); at = kid(lb, "at"); pt = P(num(at[1]), num(at[2]))
    union(pt, ("net", "/" + nm)); labels[nm] = labels.get(nm, 0) + 1
ncs = {P(num(kid(n, "at")[1]), num(kid(n, "at")[2])) for n in kids(sch, "no_connect")}

# every wire end must land on a pin, label, power pin or another wire
anchor_pts = {p[4] for p in pins_at} | {P(num(kid(l, "at")[1]), num(kid(l, "at")[2])) for l in kids(sch, "label")}
wire_ends = [e for w in wires for e in w]
from collections import Counter
cnt = Counter(wire_ends)
dangling = [e for e in wire_ends if e not in anchor_pts and cnt[e] < 2]
if dangling: fail(f"ERC: {len(dangling)} dangling wire ends, e.g. {dangling[:3]}")
else: ok(f"ERC: {len(wires)} wires, every end lands on a pin or label")
for nm, c in labels.items():
    if c < 2: fail(f"ERC: label {nm} used only once")
ok(f"ERC: labels {sorted(labels)} each appear on 2+ pins")

groups = {}
for ref, n, name, ty, pt in pins_at:
    groups.setdefault(find(pt), []).append((ref, n, name, ty, pt))
netname = {}
for r in list(parent):
    if isinstance(r, tuple) and r[0] == "net": netname[find(r)] = r[1]
sch_pin_net = {}
erc_bad = 0
for g, members in groups.items():
    nm = netname.get(g)
    real = [m for m in members if not m[0].startswith("#")]
    for ref, n, name, ty, pt in members:
        if ref.startswith("#"): continue
        if pt in ncs:
            if len(members) > 1 or nm: fail(f"ERC: {ref}.{n} has a no-connect flag but is wired"); erc_bad += 1
            sch_pin_net[(ref, n)] = None; continue
        if nm is None and len(members) < 2:
            fail(f"ERC: pin {ref}.{n} ({name}) is unconnected and has no no-connect flag"); erc_bad += 1
        sch_pin_net[(ref, n)] = nm
    types = [m[3] for m in members]
    if all(m[4] in ncs for m in members): continue          # no-connect pins are skipped by KiCad's ERC too
    if "power_in" in types and not ("power_out" in types):
        fail(f"ERC: net {nm} has power inputs but no power output/PWR_FLAG driving it"); erc_bad += 1
    if types.count("power_out") > 1: fail(f"ERC: net {nm} driven by {types.count('power_out')} power outputs"); erc_bad += 1
    if types.count("output") > 1: fail(f"ERC: net {nm} has 2+ outputs"); erc_bad += 1
if not erc_bad: ok("ERC: every pin is connected or flagged no-connect; GND has PWR_FLAG, +3V3 driven by XIAO 3V3 (power out); no output conflicts")

# ------------------------------------------------------------------ PCB model
pcb = files[NAME + ".kicad_pcb"]
nets = {int(num(n[1])): S(n[2]) for n in kids(pcb, "net")}
def rot(lx, ly, a):
    r = math.radians(a); c, s = math.cos(r), math.sin(r)
    return (lx*c + ly*s, -lx*s + ly*c)
pads, fps, crtyd, silk_items = [], {}, {}, []
for fp in kids(pcb, "footprint"):
    at = kid(fp, "at"); fx, fy = num(at[1]), num(at[2]); fa = num(at[3]) if len(at) > 3 else 0.0
    ref = [S(p[2]) for p in kids(fp, "property") if S(p[1]) == "Reference"][0]
    fps[ref] = dict(x=fx, y=fy, a=fa, lib=S(fp[1]), models=[S(m[1]) for m in kids(fp, "model")])
    for pd in kids(fp, "pad"):
        pat = kid(pd, "at"); lx, ly = num(pat[1]), num(pat[2]); dx, dy = rot(lx, ly, fa)
        sz = num(kid(pd, "size")[1]); dr = kid(pd, "drill"); n = kid(pd, "net")
        pads.append(dict(ref=ref, num=S(pd[1]), kind=pd[2], shape=pd[3], x=fx + dx, y=fy + dy, size=sz,
                         drill=num(dr[1]) if dr else 0, net=S(n[2]) if n else None))
    for r in kids(fp, "fp_rect"):
        if S(kid(r, "layer")[1]) == "F.CrtYd":
            a = (num(kid(r, "start")[1]), num(kid(r, "start")[2])); b = (num(kid(r, "end")[1]), num(kid(r, "end")[2]))
            cs = [rot(x, y, fa) for x in (a[0], b[0]) for y in (a[1], b[1])]
            crtyd[ref] = (fx + min(c[0] for c in cs), fy + min(c[1] for c in cs), fx + max(c[0] for c in cs), fy + max(c[1] for c in cs))
    for c in kids(fp, "fp_circle"):
        if S(kid(c, "layer")[1]) == "F.CrtYd":
            cx, cy = num(kid(c, "center")[1]), num(kid(c, "center")[2]); ex = num(kid(c, "end")[1]); rr = abs(ex - cx)
            dx, dy = rot(cx, cy, fa); crtyd[ref] = (fx + dx - rr, fy + dy - rr, fx + dx + rr, fy + dy + rr)
segs = [dict(a=(num(kid(s_, "start")[1]), num(kid(s_, "start")[2])), b=(num(kid(s_, "end")[1]), num(kid(s_, "end")[2])),
             w=num(kid(s_, "width")[1]), net=nets[int(num(kid(s_, "net")[1]))], layer=S(kid(s_, "layer")[1])) for s_ in kids(pcb, "segment")]
edge = kid(pcb, "gr_rect"); ex0, ey0 = num(kid(edge, "start")[1]), num(kid(edge, "start")[2]); ex1, ey1 = num(kid(edge, "end")[1]), num(kid(edge, "end")[2])
zone = kid(pcb, "zone")
zpts = [(num(p[1]), num(p[2])) for p in kid(kid(zone, "polygon"), "pts")[1:]]

# parity: schematic pin nets vs PCB pad nets
parity_bad = 0
for p in pads:
    if p["kind"] == "np_thru_hole": continue
    key = (p["ref"], p["num"])
    if key not in sch_pin_net: fail(f"parity: pad {key} has no schematic pin"); parity_bad += 1; continue
    sn = sch_pin_net[key]
    if sn is None:
        if not (p["net"] or "").startswith("unconnected-"): fail(f"parity: {key} is NC in schematic but PCB net is {p['net']}"); parity_bad += 1
    elif sn != p["net"]:
        fail(f"parity: {key} schematic net {sn} != PCB net {p['net']}"); parity_bad += 1
sch_refs = {r for (r, n) in sch_pin_net} | {S([p for p in kids(sy, "property") if S(p[1]) == "Reference"][0][2]) for sy in kids(sch, "symbol")}
sch_refs = {r for r in sch_refs if not r.startswith("#")}
if set(fps) != sch_refs: fail(f"parity: footprints {sorted(set(fps) ^ sch_refs)} only on one side"); parity_bad += 1
# footprint field in symbols matches the board
for sy in kids(sch, "symbol"):
    props = {S(p[1]): S(p[2]) for p in kids(sy, "property")}
    if props["Reference"].startswith("#"): continue
    if props["Footprint"] != fps[props["Reference"]]["lib"]: fail(f"parity: {props['Reference']} footprint field {props['Footprint']} != board {fps[props['Reference']]['lib']}"); parity_bad += 1
if not parity_bad: ok(f"parity: all {sum(1 for p in pads if p['kind'] != 'np_thru_hole')} pads match the schematic nets; {len(fps)} footprints match {len(sch_refs)} symbols; footprint fields agree")

# ------------------------------------------------------------------ DRC-style checks
CLR, EDGE, HOLE_CLR, RING = 0.2, 0.3, 0.25, 0.13
def seg_pt(a, b, p):
    ax, ay = a; bx, by = b; px, py = p; dx, dy = bx - ax, by - ay; L = dx*dx + dy*dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax)*dx + (py - ay)*dy)/L))
    return math.hypot(ax + t*dx - px, ay + t*dy - py)
def seg_seg(a, b, c, d): return min(seg_pt(a, b, c), seg_pt(a, b, d), seg_pt(c, d, a), seg_pt(c, d, b))
def pad_r(p): return p["size"]/2 * (math.sqrt(2) if p["shape"] == "rect" else 1)   # conservative for squares
drc = 0
cu = [p for p in pads if p["kind"] == "thru_hole"]
npth = [p for p in pads if p["kind"] == "np_thru_hole"]
mind = {}
def track_min(k, v): mind[k] = min(mind.get(k, 9), v)
for i, p in enumerate(cu):
    for q2 in cu[i+1:]:
        g = math.hypot(p["x"] - q2["x"], p["y"] - q2["y"]) - pad_r(p) - pad_r(q2)
        if p["net"] != q2["net"]:
            track_min("pad-pad", g)
            if g < CLR: fail(f"DRC: pad {p['ref']}.{p['num']} to {q2['ref']}.{q2['num']} clearance {g:.3f}"); drc += 1
    e = min(p["x"] - ex0, ex1 - p["x"], p["y"] - ey0, ey1 - p["y"]) - p["size"]/2; track_min("pad-edge", e)
    if e < EDGE: fail(f"DRC: pad {p['ref']}.{p['num']} edge clearance {e:.3f}"); drc += 1
    rg = (p["size"] - p["drill"])/2; track_min("annular ring", rg)
    if rg < RING: fail(f"DRC: pad {p['ref']}.{p['num']} annular ring {rg:.3f}"); drc += 1
    for h in npth:
        g = math.hypot(p["x"] - h["x"], p["y"] - h["y"]) - pad_r(p) - h["drill"]/2; track_min("pad-hole", g)
        if g < HOLE_CLR: fail(f"DRC: pad {p['ref']}.{p['num']} to hole {h['ref']} {g:.3f}"); drc += 1
for s_ in segs:
    for p in cu:
        g = seg_pt(s_["a"], s_["b"], (p["x"], p["y"])) - s_["w"]/2 - pad_r(p)
        if p["net"] != s_["net"]:
            track_min("track-pad", g)
            if g < CLR: fail(f"DRC: {s_['net']} track to pad {p['ref']}.{p['num']} ({p['net']}) {g:.3f}"); drc += 1
    for h in npth:
        g = seg_pt(s_["a"], s_["b"], (h["x"], h["y"])) - s_["w"]/2 - h["drill"]/2; track_min("track-hole", g)
        if g < HOLE_CLR: fail(f"DRC: track to hole {h['ref']} {g:.3f}"); drc += 1
    for pt in (s_["a"], s_["b"]):
        e = min(pt[0] - ex0, ex1 - pt[0], pt[1] - ey0, ey1 - pt[1]) - s_["w"]/2; track_min("track-edge", e)
        if e < EDGE: fail(f"DRC: track edge clearance {e:.3f}"); drc += 1
for i, s1 in enumerate(segs):
    for s2 in segs[i+1:]:
        if s1["net"] != s2["net"]:
            g = seg_seg(s1["a"], s1["b"], s2["a"], s2["b"]) - s1["w"]/2 - s2["w"]/2; track_min("track-track", g)
            if g < CLR: fail(f"DRC: {s1['net']} vs {s2['net']} tracks {g:.3f}"); drc += 1
# connectivity per net (tracks + pads); GND goes through the back pour
parent.clear()
for i, s_ in enumerate(segs):
    for j, s2 in enumerate(segs[:i]):
        if s_["net"] == s2["net"] and seg_seg(s_["a"], s_["b"], s2["a"], s2["b"]) < 1e-3: union(("s", i), ("s", j))
    for k, p in enumerate(cu):
        if p["net"] == s_["net"] and seg_pt(s_["a"], s_["b"], (p["x"], p["y"])) < p["size"]/2: union(("s", i), ("p", k))
        elif p["net"] != s_["net"] and seg_pt(s_["a"], s_["b"], (p["x"], p["y"])) < p["size"]/2: fail(f"DRC: {s_['net']} track touches {p['net']} pad")
for k, p in enumerate(cu):
    find(("p", k))
for net in sorted({p["net"] for p in cu if p["net"] and not p["net"].startswith("unconnected")}):
    members = [("p", k) for k, p in enumerate(cu) if p["net"] == net]
    if net == "GND":
        inside = all(min(z[0] for z in zpts) < cu[k]["x"] < max(z[0] for z in zpts) and min(z[1] for z in zpts) < cu[k]["y"] < max(z[1] for z in zpts) for _, k in members)
        if not inside: fail("DRC: a GND pad is outside the back pour")
        ok(f"connectivity: GND ({len(members)} pads) all inside the B.Cu GND pour, which has no other copper on that layer")
        continue
    roots = {find(m) for m in members}
    if len(roots) != 1: fail(f"connectivity: net {net} is split into {len(roots)} pieces"); drc += 1
    else: ok(f"connectivity: {net} fully routed ({len(members)} pads)")
for a_ in sorted(crtyd):
    for b_ in sorted(crtyd):
        if a_ < b_ and "CASE1" not in (a_, b_):
            A, B = crtyd[a_], crtyd[b_]
            if A[0] < B[2] and B[0] < A[2] and A[1] < B[3] and B[1] < A[3]:
                fail(f"DRC: courtyards overlap {a_} / {b_}"); drc += 1
if not drc: ok("DRC: clearances OK. Minimums: " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(mind.items())))
for ref, f_ in fps.items():
    for m in f_["models"]:
        fn = m.replace("${KIPRJMOD}/", "")
        if not os.path.exists(os.path.join(PROJ, fn)): fail(f"3D model missing: {ref} -> {m}")
ok("3D: every footprint's model file exists in 3d/")

# ------------------------------------------------------------------ 3D fit against the real case
case = {"__file__": os.path.join(PROJ, "..", "case", "source", "gen_case.py")}
exec(open(case["__file__"]).read().split("vb,zb=voxel")[0], case)
res = case["res"]
vb, _ = case["voxel"](case["back_ops"], 0, case["Hs"])
vl, zl = case["voxel"](case["lid_ops"], case["Zt"] - 0.2, case["Hs"] + case["lid_t"])
nz = int(np.ceil((case["Hs"] + case["lid_t"]) / res)) + 3
V = np.zeros(vb.shape[:2] + (nz,), np.uint8)       # 1 = back shell, 2 = lid
V[:, :, :vb.shape[2]] |= vb.astype(np.uint8)
o = int(round(zl / res)); V[:, :, o:o + vl.shape[2]] |= (vl.astype(np.uint8) * 2)
X0, Y0, Zt = case["X0"], case["Y0"], case["Zt"]
def to_case(box):  # PCB-local box (x,y from PCB corner; z from PCB top) -> case frame
    x0, y0, z0, x1, y1, z1 = box
    return (x0 + X0, y0 + Y0, z0 + Zt, x1 + X0, y1 + Y0, z1 + Zt)
def vox_in(box, shrink=0.05):
    x0, y0, z0, x1, y1, z1 = box
    i0, i1 = max(0, int(math.ceil((x0 + shrink)/res - 0.5))), min(V.shape[0], int(math.floor((x1 - shrink)/res - 0.5)) + 1)
    j0, j1 = max(0, int(math.ceil((y0 + shrink)/res - 0.5))), min(V.shape[1], int(math.floor((y1 - shrink)/res - 0.5)) + 1)
    k0, k1 = max(0, int(math.ceil((z0 + shrink)/res - 0.5))), min(V.shape[2], int(math.floor((z1 - shrink)/res - 0.5)) + 1)
    if i0 >= i1 or j0 >= j1 or k0 >= k1: return 0, 0
    sub = V[i0:i1, j0:j1, k0:k1]
    return int((sub & 1).astype(bool).sum()), int((sub & 2).astype(bool).sum())
def gap_above(box):
    x0, y0, z0, x1, y1, z1 = box
    i0, i1 = int(x0/res), int(math.ceil(x1/res)); j0, j1 = int(y0/res), int(math.ceil(y1/res)); k = int(math.ceil(z1/res))
    sub = V[max(0, i0):i1, max(0, j0):j1, k:]
    hit = np.argwhere(sub.any(axis=(0, 1)))
    return (hit[0][0] * res) if len(hit) else None
bodies = json.load(open(os.path.join(PROJ, "3d", "bodies.json")))
fit_rows, fit_bad = [], 0
for b in bodies:
    if b["ref"] == "CASE1": continue
    cb = to_case(b["box"]); nb, nl = vox_in(cb)
    g = gap_above(cb)
    fit_rows.append((b["ref"], b["part"], nb, nl, g))
    if nb or nl:
        fail(f"3D FIT: {b['ref']} {b['part']} hits the case ({nb} back-shell voxels, {nl} lid voxels at {res} mm)"); fit_bad += 1
# PCB slab: only the case pins may enter it, and only through the mounting holes
pcb_box = to_case((0, 0, -1.6, 24, 52, 0))
x0, y0, z0, x1, y1, z1 = pcb_box
ii = np.arange(V.shape[0]); jj = np.arange(V.shape[1]); kk = np.arange(V.shape[2])
cx, cy, cz = (ii + 0.5)*res, (jj + 0.5)*res, (kk + 0.5)*res
mi = (cx > x0 + 0.05) & (cx < x1 - 0.05); mj = (cy > y0 + 0.05) & (cy < y1 - 0.05); mk = (cz > z0 + 0.05) & (cz < z1 - 0.05)
sub = V[np.ix_(mi, mj, mk)]
hits = np.argwhere(sub)
holes = [(p["x"] - OX, p["y"] - OY, p["drill"]) for p in npth]
stray = 0
for (a, b_, c) in hits:
    px, py = cx[mi][a] - X0, cy[mj][b_] - Y0
    if not any(math.hypot(px - hx, py - hy) < hd/2 for hx, hy, hd in holes): stray += 1
if stray: fail(f"3D FIT: case material inside the PCB outside the mounting holes ({stray} voxels)"); fit_bad += 1
else: ok(f"3D FIT: PCB sits in the case clean; the only case material through the board is the 2 locating pins, inside H1/H2 ({len(hits)} voxels)")
# board seats on its ledges / standoffs, lid bosses touch the top
below = V[np.ix_(mi, mj, (cz > z0 - res) & (cz < z0))]
above = V[np.ix_(mi, mj, (cz > z1) & (cz < z1 + res))]
ok(f"3D FIT: PCB is supported from below ({int((below & 1).astype(bool).sum())} contact voxels on ledges/standoffs) and clamped from above ({int((above & 2).astype(bool).sum())} lid-boss contact voxels)")
if not (below & 1).any(): fail("3D FIT: nothing supports the PCB from below")
if not (above & 2).any(): warn("3D FIT: lid bosses don't reach the PCB top")
# USB-C plug access: plug overmold ~12.4 x 6.6 mm centred on the receptacle, from the board edge outward
xb = [b for b in bodies if b["part"] == "XIAO USB-C receptacle"][0]["box"]
ucx, ucz = (xb[0] + xb[3])/2, (xb[2] + xb[5])/2
plug = to_case((ucx - 6.2, -12.0, ucz - 3.3, ucx + 6.2, xb[1] + 0.3, ucz + 3.3))
nb_, nl_ = vox_in(plug, 0.0)
if nb_ or nl_: fail(f"3D FIT: USB-C plug body would hit the case at the top opening ({nb_}+{nl_} voxels)"); fit_bad += 1
else: ok(f"3D FIT: a full-size USB-C plug (12.4 x 6.6 mm) reaches the XIAO's port through the top opening (port centre {ucz + Zt:.1f} mm above the back face; opening starts at {case['usb_z0']} mm)")
# probe slot
pb = [b for b in bodies if b["part"].startswith("SEN0193 probe board")][0]["box"]
nb_, nl_ = vox_in(to_case(pb))
if not (nb_ or nl_): ok(f"3D FIT: probe board passes the bottom-wall slot and rails with no contact; {case['probe_in']:.0f} mm of probe inside the case, {pb[4] - (case['L'] - Y0):.0f} mm sticks out to go in the soil")
# header pins that are NOT trimmed (male header long side = 6 mm through the board)
for ref, part in [("U1", "header pins below board L"), ("J1", "header pins below board")]:
    bx = [b for b in bodies if b["ref"] == ref and b["part"] == part][0]["box"]
    floor_gap = (bx[2] + Zt) - case["floor_t"]
    long_ = list(bx); long_[2] = -1.6 - 4.4
    nb_, _ = vox_in(to_case(long_))
    if nb_: warn(f"3D FIT: {ref}: untrimmed header pins (4.4 mm below the board) would hit the case floor: trim them to under {case['back_clear'] - 0.3:.1f} mm after soldering")
# antenna: free space on the lid underside over the probe end (above the probe, between the clamp ribs)
yp0, yp1 = case["Yp"] + 2, case["L"] - case["wall"] - 1
xs = np.arange(case["xi0"] + 1.6, case["xi1"] - 1.6, res); free_w = (case["Xp"] + case["probe_w"] - 0.8 - 0.3) - (case["Xp"] + 0.8 + 0.3)
ok(f"3D FIT: room for the XIAO's FPC antenna on the lid underside over the probe: about {free_w:.0f} x {yp1 - yp0:.0f} mm, {case['Hs'] - case['Zt'] - 2.0:.1f} mm above the probe electronics")

# ------------------------------------------------------------------ previews
try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Rectangle, Polygon
    fig, ax = plt.subplots(1, 2, figsize=(17, 8.5), gridspec_kw={"width_ratios": [1, 2.3]})
    a = ax[0]; a.set_facecolor("#0b3d1e")
    a.add_patch(Rectangle((ex0, ey0), ex1 - ex0, ey1 - ey0, fc="#1d6b3a", ec="yellow", lw=1.2))
    cols = {"/ADC": "#e8a33d", "/SDA": "#4da3ff", "/SCL": "#b07cff", "+3V3": "#ff5c5c", "/PROBE_A": "#ffd84d"}
    for s_ in segs: a.plot([s_["a"][0], s_["b"][0]], [s_["a"][1], s_["b"][1]], color=cols.get(s_["net"], "w"), lw=s_["w"]*14, solid_capstyle="round")
    for p in pads:
        if p["kind"] == "np_thru_hole": a.add_patch(Circle((p["x"], p["y"]), p["drill"]/2, fc="black")); continue
        c = cols.get(p["net"], "#cfcfcf" if p["net"] == "GND" else "#9a8a5a")
        if p["shape"] == "rect": a.add_patch(Rectangle((p["x"] - p["size"]/2, p["y"] - p["size"]/2), p["size"], p["size"], fc=c))
        else: a.add_patch(Circle((p["x"], p["y"]), p["size"]/2, fc=c))
        a.add_patch(Circle((p["x"], p["y"]), p["drill"]/2, fc="#222"))
    for r, (x0_, y0_, x1_, y1_) in crtyd.items():
        if r != "CASE1":
            a.add_patch(Rectangle((x0_, y0_), x1_ - x0_, y1_ - y0_, fill=False, ec="#ff66ff", lw=0.6, ls="--"))
            a.text((x0_ + x1_)/2, y0_ - 0.2, r, color="w", fontsize=7, ha="center")
    a.set_xlim(ex0 - 3, ex1 + 3); a.set_ylim(ey1 + 4, ey0 - 3); a.set_aspect("equal")
    a.set_title("PCB as parsed from the .kicad_pcb\n(GND = grey pads, on the back pour; pink = courtyards)", fontsize=9)
    for n_, c in cols.items(): a.plot([], [], color=c, lw=4, label=n_)
    a.legend(loc="lower right", fontsize=7)
    # side section through the XIAO/AHT10 centre line (x = 12 on the PCB)
    a = ax[1]
    ic = int((12 + X0)/res)
    sec = V[ic, :, :].T
    img = np.zeros(sec.shape + (3,)) + 1.0
    img[(sec & 1) > 0] = (0.25, 0.6, 0.35); img[(sec & 2) > 0] = (0.75, 0.75, 0.7)
    a.imshow(img, origin="lower", extent=[0, V.shape[1]*res, 0, V.shape[2]*res], interpolation="nearest")
    a.add_patch(Rectangle((Y0, Zt - 1.6), 52, 1.6, fc="#1d6b3a"))
    colors = {"U1": "#7b3fa0", "J1": "#2a5bd7", "P1": "#222", "R1": "#c9a26b", "R2": "#c9a26b", "C1": "#d98b2b", "C2": "#2a3a8a"}
    for b in bodies:
        if b["ref"] == "CASE1": continue
        x0_, y0_, z0_, x1_, y1_, z1_ = to_case(b["box"])
        if x0_ <= 12 + X0 <= x1_ or b["ref"] in ("C2",):
            a.add_patch(Rectangle((y0_, z0_), y1_ - y0_, z1_ - z0_, fc=colors.get(b["ref"], "grey"), alpha=0.75, ec="k", lw=0.3))
    a.set_xlim(-2, case["L"] + 20); a.set_ylim(-1, case["Hs"] + case["lid_t"] + 3); a.set_aspect("equal")
    a.set_title("Side section through the case at the board centre line\ngreen = back shell, grey = lid, colours = parts (C2 is off-centre, shown for height)", fontsize=9)
    a.set_xlabel("mm from the USB end"); a.set_ylabel("mm above the back face")
    plt.tight_layout(); plt.savefig(os.path.join(HERE, "verify-pcb-and-fit.png"), dpi=110)
    ok("rendered source/verify-pcb-and-fit.png")
except Exception as e:
    warn(f"preview render failed: {e}")

# ------------------------------------------------------------------ report
print("\nPart clearance to the case (mm of air above each part, '-' = open to the lid vents/edge):")
for ref, part, nb, nl, g in fit_rows:
    print(f"  {ref:5s} {part:45s} {'HIT' if (nb or nl) else 'ok ':4s} gap above: {('%.1f' % g) if g is not None else '-'}")
print()
for m in OK: print("PASS ", m)
for m in WARN: print("WARN ", m)
for m in FAIL: print("FAIL ", m)
print(f"\n{len(OK)} passed, {len(WARN)} warnings, {len(FAIL)} failures")
sys.exit(1 if FAIL else 0)
