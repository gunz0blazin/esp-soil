"""Plot fab files (RS-274X Gerbers + Excellon drills) straight from esp-soil-stake.kicad_pcb.

For when KiCad isn't at hand. Reads pads, tracks, outline, silkscreen and the GND zone from the
board file and writes the same layer set KiCad's plotter would:
  F_Cu.gtl  B_Cu.gbl  F_Mask.gts  B_Mask.gbs  F_Silkscreen.gto  B_Silkscreen.gbo  Edge_Cuts.gm1
  PTH.drl  NPTH.drl     -> ../gerbers/  and  ../gerbers/esp-soil-stake-v1.1-gerbers.zip
The back GND pour is filled here using the zone's own settings (0.3 mm clearance, 0.5 mm
thermal gap / spokes, 0.5 mm from the edge). Text is drawn with a real outline font.
Run: python3 gen_gerbers.py
"""
import os, math, zipfile
import numpy as np
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "verify_kicad.py")).read().split("# ------------------------------------------------------------------ schematic connectivity")[0]
     .split("try:\n    sys.path.insert")[0])
pcb = files[NAME + ".kicad_pcb"]
OUT = os.path.join(PROJ, "gerbers"); os.makedirs(OUT, exist_ok=True)
REV = "1.1"
MASK_EXP = 0.05          # solder mask opening grows 0.05 mm per side
SILK_PAD_CLR = 0.15      # silkscreen clipped this far from mask openings

def rot(lx, ly, a):
    r = math.radians(a); c, s = math.cos(r), math.sin(r)
    return (lx*c + ly*s, -lx*s + ly*c)

# ------------------------------------------------------------------ read the board
nets = {int(num(n[1])): S(n[2]) for n in kids(pcb, "net")}
pads, silk, silk_text = [], [], []      # silk: (layer, kind, data, width)
for fp in kids(pcb, "footprint"):
    at = kid(fp, "at"); fx, fy = num(at[1]), num(at[2]); fa = num(at[3]) if len(at) > 3 else 0.0
    def B(lx, ly):
        dx, dy = rot(lx, ly, fa); return (fx + dx, fy + dy)
    for pd in kids(fp, "pad"):
        pat = kid(pd, "at"); x, y = B(num(pat[1]), num(pat[2]))
        n = kid(pd, "net"); dr = kid(pd, "drill")
        pads.append(dict(kind=pd[2], shape=pd[3], x=x, y=y, size=num(kid(pd, "size")[1]),
                         drill=num(dr[1]) if dr else 0.0, net=S(n[2]) if n else None, angle=fa))
    for g in kids(fp, "fp_line") + kids(fp, "fp_rect") + kids(fp, "fp_circle"):
        layer = S(kid(g, "layer")[1])
        if layer not in ("F.SilkS", "B.SilkS"): continue
        w = num(kid(kid(g, "stroke"), "width")[1])
        if g[0] == "fp_circle":
            c = (num(kid(g, "center")[1]), num(kid(g, "center")[2])); e = (num(kid(g, "end")[1]), num(kid(g, "end")[2]))
            silk.append((layer, "circle", (B(*c), math.hypot(e[0]-c[0], e[1]-c[1])), w))
        else:
            a_ = (num(kid(g, "start")[1]), num(kid(g, "start")[2])); b_ = (num(kid(g, "end")[1]), num(kid(g, "end")[2]))
            pts = [a_, b_] if g[0] == "fp_line" else [a_, (b_[0], a_[1]), b_, (a_[0], b_[1]), a_]
            silk.append((layer, "poly", [B(*p) for p in pts], w))
    texts = [t for t in kids(fp, "fp_text")] + [p for p in kids(fp, "property") if S(p[1]) == "Reference"]
    ref = [S(p[2]) for p in kids(fp, "property") if S(p[1]) == "Reference"][0]
    for t in texts:
        layer = S(kid(t, "layer")[1])
        if layer not in ("F.SilkS", "B.SilkS") or kid(t, "hide"): continue
        s_ = S(t[2]).replace("${REFERENCE}", ref)
        tat = kid(t, "at"); x, y = B(num(tat[1]), num(tat[2]))
        size = num(kid(kid(kid(t, "effects"), "font"), "size")[1])
        silk_text.append((layer, s_, x, y, size, False))
for t in kids(pcb, "gr_text"):
    layer = S(kid(t, "layer")[1]); tat = kid(t, "at")
    eff = kid(t, "effects"); size = num(kid(kid(eff, "font"), "size")[1])
    mirror = any(isinstance(j, list) and j[0] == "justify" and "mirror" in j for j in eff)
    silk_text.append((layer, S(t[1]), num(tat[1]), num(tat[2]), size, mirror))
segs = [dict(a=(num(kid(s_, "start")[1]), num(kid(s_, "start")[2])), b=(num(kid(s_, "end")[1]), num(kid(s_, "end")[2])),
             w=num(kid(s_, "width")[1]), net=nets[int(num(kid(s_, "net")[1]))]) for s_ in kids(pcb, "segment")]
edge = kid(pcb, "gr_rect")
EX0, EY0 = num(kid(edge, "start")[1]), num(kid(edge, "start")[2]); EX1, EY1 = num(kid(edge, "end")[1]), num(kid(edge, "end")[2])
zone = kid(pcb, "zone")
ZCLR = num(kid(zone, "connect_pads")[1][1]) if kid(kid(zone, "connect_pads"), "clearance") else 0.3
zfill = kid(zone, "fill"); TGAP = num(kid(zfill, "thermal_gap")[1]); TSPOKE = num(kid(zfill, "thermal_bridge_width")[1])
ZPTS = [(num(p[1]), num(p[2])) for p in kid(kid(zone, "polygon"), "pts")[1:]]

# ------------------------------------------------------------------ Gerber writer (board coords; Gerber Y is up)
def fmt(v): return str(int(round(v * 1e6)))
def XY(x, y): return f"X{fmt(x - EX0)}Y{fmt(EY1 - y)}"      # origin = board bottom-left
class G:
    def __init__(s, fn, func, polarity="Positive"):
        s.fn = fn; s.head = ["%TF.GenerationSoftware,esp-soil,gen_gerbers.py,1.1*%", f"%TF.FileFunction,{func}*%",
                             f"%TF.FilePolarity,{polarity}*%", "%FSLAX46Y46*%", "%MOMM*%"]
        s.aps, s.body, s.n = {}, ["%LPD*%", "G01*"], 10
    def ap(s, spec):
        if spec not in s.aps: s.aps[spec] = s.n; s.n += 1
        return s.aps[spec]
    def use(s, spec): s.body.append(f"D{s.ap(spec)}*")
    def flash(s, spec, x, y): s.use(spec); s.body.append(XY(x, y) + "D03*")
    def line(s, spec, pts):
        s.use(spec); s.body.append(XY(*pts[0]) + "D02*")
        for p in pts[1:]: s.body.append(XY(*p) + "D01*")
    def region(s, pts):
        s.body.append("G36*"); s.body.append(XY(*pts[0]) + "D02*")
        for p in list(pts[1:]) + [pts[0]]: s.body.append(XY(*p) + "D01*")
        s.body.append("G37*")
    def dark(s, d): s.body.append("%LPD*%" if d else "%LPC*%")
    def save(s):
        ad = [f"%ADD{n}{spec}*%" for spec, n in sorted(s.aps.items(), key=lambda kv: kv[1])]
        open(os.path.join(OUT, s.fn), "w").write("\n".join(s.head + ad + s.body + ["M02*"]) + "\n")
        return s.fn
def C(d): return f"C,{d:.4f}"
def R(w, h=None): return f"R,{w:.4f}X{(h if h else w):.4f}"
def O(w, h=None): return f"O,{w:.4f}X{(h if h else w):.4f}"
def pad_ap(p, grow=0.0):
    d = p["size"] + 2*grow
    if p["shape"] == "rect": return R(d)
    if p["shape"] == "oval": return O(d)
    return C(d)

# ------------------------------------------------------------------ text -> filled outlines
FONT = FontProperties(family="DejaVu Sans", weight="bold")
def text_polys(s_, x, y, size, mirror):
    """KiCad-style: 'size' = glyph height, centred on (x, y). Returns [(points, is_hole)]."""
    tp = TextPath((0, 0), s_, size=size / 0.73, prop=FONT)     # cap height ~0.73 em in DejaVu
    bb = tp.get_extents()
    out = []
    for poly in tp.to_polygons():
        P = np.asarray(poly)
        if len(P) < 3: continue
        cx = (bb.x0 + bb.x1) / 2; cy = (bb.y0 + bb.y1) / 2
        px = (P[:, 0] - cx) * (-1 if mirror else 1) + x
        py = y - (P[:, 1] - cy)
        area = 0.5 * np.sum(px[:-1]*py[1:] - px[1:]*py[:-1])
        out.append((list(zip(px, py)), area))
    # outer contours vs holes: a contour inside another contour of the same glyph set is a hole
    def inside(pt, poly):
        xq, yq = pt; n = len(poly); c = False
        for i in range(n):
            x1, y1 = poly[i]; x2, y2 = poly[(i+1) % n]
            if (y1 > yq) != (y2 > yq) and xq < (x2 - x1)*(yq - y1)/(y2 - y1 + 1e-12) + x1: c = not c
        return c
    res = []
    for i, (pts, ar) in enumerate(out):
        depth = sum(1 for j, (q, _) in enumerate(out) if j != i and inside(pts[0], q))
        res.append((pts, depth % 2 == 1))
    return res

# ------------------------------------------------------------------ layers
files_out = []
cu_pads = [p for p in pads if p["kind"] == "thru_hole"]
np_holes = [p for p in pads if p["kind"] == "np_thru_hole"]

# top copper: pads + tracks
g = G("esp-soil-stake-F_Cu.gtl", "Copper,L1,Top")
for p in cu_pads: g.flash(pad_ap(p), p["x"], p["y"])
for s_ in segs: g.line(C(s_["w"]), [s_["a"], s_["b"]])
files_out.append(g.save())

# bottom copper: pads + GND pour (zone outline, minus clearances, thermal reliefs on GND pads)
g = G("esp-soil-stake-B_Cu.gbl", "Copper,L2,Bot")
g.region(ZPTS)
g.dark(False)
for p in cu_pads:
    if p["net"] == "GND": g.flash(pad_ap(p, TGAP), p["x"], p["y"])
    else: g.flash(pad_ap(p, ZCLR), p["x"], p["y"])
for h in np_holes: g.flash(C(h["drill"] + 2*0.5), h["x"], h["y"])
g.dark(True)
for p in cu_pads:
    if p["net"] == "GND":                       # 4 spokes from pad edge across the gap into the pour
        r = p["size"]/2 + TGAP + 0.2
        for dx, dy in [(r, 0), (-r, 0), (0, r), (0, -r)]:
            g.line(C(TSPOKE), [(p["x"], p["y"]), (p["x"] + dx, p["y"] + dy)])
for p in cu_pads: g.flash(pad_ap(p), p["x"], p["y"])
files_out.append(g.save())

# solder masks (negative-image openings): pads + NPTH holes
for fn, func in [("esp-soil-stake-F_Mask.gts", "Soldermask,Top"), ("esp-soil-stake-B_Mask.gbs", "Soldermask,Bot")]:
    g = G(fn, func, "Negative")
    for p in cu_pads: g.flash(pad_ap(p, MASK_EXP), p["x"], p["y"])
    for h in np_holes: g.flash(C(h["drill"] + 2*MASK_EXP), h["x"], h["y"])
    files_out.append(g.save())

# silkscreens, clipped away from mask openings
for layer, fn, func in [("F.SilkS", "esp-soil-stake-F_Silkscreen.gto", "Legend,Top"), ("B.SilkS", "esp-soil-stake-B_Silkscreen.gbo", "Legend,Bot")]:
    g = G(fn, func)
    for (ly, kind, d, w) in silk:
        if ly != layer: continue
        if kind == "poly": g.line(C(w), d)
        else:
            (cx, cy), r = d
            g.line(C(w), [(cx + r*math.cos(t), cy + r*math.sin(t)) for t in np.linspace(0, 2*math.pi, 49)])
    for (ly, s_, x, y, size, mirror) in silk_text:
        if ly != layer: continue
        polys = text_polys(s_, x, y, size, mirror)
        for pts, hole in polys:
            if not hole: g.region(pts)
        holes = [pts for pts, hole in polys if hole]
        if holes:
            g.dark(False)
            for pts in holes: g.region(pts)
            g.dark(True)
    g.dark(False)
    for p in cu_pads: g.flash(pad_ap(p, MASK_EXP + SILK_PAD_CLR), p["x"], p["y"])
    for h in np_holes: g.flash(C(h["drill"] + 2*(MASK_EXP + SILK_PAD_CLR)), h["x"], h["y"])
    files_out.append(g.save())

# board outline
g = G("esp-soil-stake-Edge_Cuts.gm1", "Profile,NP")
g.line(C(0.1), [(EX0, EY0), (EX1, EY0), (EX1, EY1), (EX0, EY1), (EX0, EY0)])
files_out.append(g.save())

# drills (Excellon, metric, absolute, same origin as the Gerbers)
def drill(fn, items, plated):
    tools = {}
    for d, x, y in items: tools.setdefault(round(d, 3), []).append((x, y))
    L = ["M48", f"; esp-soil stake v{REV} {'PTH' if plated else 'NPTH'} drill file, gen_gerbers.py",
         f"; #@! TF.FileFunction,{'Plated' if plated else 'NonPlated'},1,2,{'PTH' if plated else 'NPTH'}", "FMAT,2", "METRIC"]
    for i, d in enumerate(sorted(tools), 1): L.append(f"T{i}C{d:.3f}")
    L += ["%", "G90", "G05"]
    for i, d in enumerate(sorted(tools), 1):
        L.append(f"T{i}")
        for x, y in tools[d]: L.append(f"X{x - EX0:.3f}Y{EY1 - y:.3f}")
    L += ["M30"]
    open(os.path.join(OUT, fn), "w").write("\n".join(L) + "\n"); return fn
files_out.append(drill("esp-soil-stake-PTH.drl", [(p["drill"], p["x"], p["y"]) for p in cu_pads], True))
files_out.append(drill("esp-soil-stake-NPTH.drl", [(h["drill"], h["x"], h["y"]) for h in np_holes], False))

zfn = os.path.join(OUT, f"esp-soil-stake-v{REV}-gerbers.zip")
with zipfile.ZipFile(zfn, "w", zipfile.ZIP_DEFLATED) as z:
    for f_ in files_out: z.write(os.path.join(OUT, f_), f_)
print(f"{len(files_out)} files -> {zfn}")
print(f"board {EX1-EX0:.1f} x {EY1-EY0:.1f} mm | {len(cu_pads)} plated holes, {len(np_holes)} mounting holes, {len(segs)} track segments")
