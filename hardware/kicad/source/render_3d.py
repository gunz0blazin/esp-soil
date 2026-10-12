"""Render what KiCad's 3D viewer should show, straight from the .kicad_pcb + the .wrl files.
Reads each footprint's position/rotation and model list from the board file, loads the VRML
(KiCad convention: 1 unit = 0.1 in, y up), applies the footprint transform, and draws it.
Output: source/render-3d.png. Useful to confirm the models line up before opening KiCad."""
import os, re, math, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_kicad.py")).read().split("# ------------------------------------------------------------------ schematic connectivity")[0]
     .split("try:\n    sys.path.insert")[0])

pcb = files[NAME + ".kicad_pcb"]
def load_wrl(path):
    """Handles both our models and KiCad's StepUp models (DEF/USE materials, coordIndex before point)."""
    s = open(path).read()
    mats = {}
    for m in re.finditer(r"DEF\s+(\S+)\s+Material\s*\{([^}]*)\}", s):
        body = m.group(2)
        c = re.search(r"diffuseColor\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", body); t = re.search(r"transparency\s+([\d.]+)", body)
        mats[m.group(1)] = (tuple(float(x) for x in c.groups()) if c else (0.6, 0.6, 0.6), float(t.group(1)) if t else 0.0)
    out = []
    for blk in re.split(r"(?=Shape\s*\{)", s):
        pt = re.search(r"point\s*\[([^\]]*)\]", blk); ci = re.search(r"coordIndex\s*\[([^\]]*)\]", blk)
        if not (pt and ci): continue
        c = re.search(r"diffuseColor\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", blk); t = re.search(r"transparency\s+([\d.]+)", blk)
        u = re.search(r"USE\s+(\S+?)\s*\}", blk)
        if c: rgb, tr = tuple(float(x) for x in c.groups()), float(t.group(1)) if t else 0.0
        elif u and u.group(1) in mats: rgb, tr = mats[u.group(1)]
        else: rgb, tr = (0.6, 0.6, 0.6), 0.0
        P = np.array(pt.group(1).replace(",", " ").split(), float).reshape(-1, 3) * 2.54
        polys, cur = [], []
        for i in (int(x) for x in ci.group(1).replace(",", " ").split()):
            if i < 0:
                if len(cur) >= 3: polys.append(cur)
                cur = []
            else: cur.append(i)
        out.append((P, polys, rgb, tr))
    return out

def fp_shapes(skip_lid=False):
    shapes = []
    for fp in kids(pcb, "footprint"):
        at = kid(fp, "at"); fx, fy = num(at[1]), num(at[2]); fa = math.radians(num(at[3]) if len(at) > 3 else 0)
        for m in kids(fp, "model"):
            fn = S(m[1]).replace("${KIPRJMOD}/", "")
            if skip_lid and "lid" in fn: continue
            for P, polys, rgb, tr in load_wrl(os.path.join(PROJ, fn)):
                x, y, z = P[:, 0], P[:, 1], P[:, 2]              # VRML: y up == -board y
                # rotate in the VRML (y-up) frame by +angle (CCW), then flip y into board coords
                xr = x*math.cos(fa) - y*math.sin(fa); yr = x*math.sin(fa) + y*math.cos(fa)
                Q = np.c_[fx + xr, fy - yr, z]
                shapes.append((Q, polys, rgb, tr, fn))
    return shapes

def draw(ax, shapes, elev, azim, title, lid_alpha=None, lims=((95, 135), (-185, -95), (-15, 25)), board=True):
    """One collection so matplotlib depth-sorts every face together. Board y is flipped to +y up
    (same as KiCad's 3D viewer) instead of inverting the axis, so the camera stays above the board."""
    verts, cols = [], []
    def add(V, rgba, maxe=2.0):
        """split big faces into small triangles so per-face depth sorting works"""
        tris = [V[[0, i, i + 1]] for i in range(1, len(V) - 1)]
        while tris:
            t = tris.pop()
            e = [np.linalg.norm(t[1] - t[0]), np.linalg.norm(t[2] - t[1]), np.linalg.norm(t[0] - t[2])]
            if max(e) <= maxe:
                verts.append(t); cols.append(rgba); continue
            a, b, c = t; ab, bc, ca = (a + b)/2, (b + c)/2, (c + a)/2
            tris += [np.array(x) for x in ([a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca])]
    if board:
        bd = np.array([[100, -100], [124, -100], [124, -152], [100, -152]])
        for zz in (0.0, -1.6):
            add(np.c_[bd, np.full(4, zz)], (0.11, 0.42, 0.23, 1.0))
        for (a, b) in [(0, 1), (1, 2), (2, 3), (3, 0)]:
            add(np.array([[*bd[a], 0], [*bd[b], 0], [*bd[b], -1.6], [*bd[a], -1.6]]), (0.08, 0.3, 0.16, 1.0))
    for Q, polys, rgb, tr, fn in shapes:
        alpha = 1 - tr
        if lid_alpha is not None and "lid" in fn: alpha = lid_alpha
        Qf = np.c_[Q[:, 0], -Q[:, 1], Q[:, 2]]
        step = 2 if len(polys) > 40000 else 1
        for p_ in polys[::step]:
            add(Qf[p_], (*rgb, alpha))
    pc = Poly3DCollection(verts, facecolors=cols, edgecolors="none")
    ax.add_collection3d(pc)
    (x0, x1), (y0, y1), (z0, z1) = lims
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_zlim(z0, z1)
    ax.set_box_aspect((x1 - x0, y1 - y0, z1 - z0)); ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off(); ax.set_title(title, fontsize=10)

shapes_open = fp_shapes(skip_lid=True)
fig = plt.figure(figsize=(16, 9))
ax1 = fig.add_subplot(1, 3, 1, projection="3d")
draw(ax1, shapes_open, 40, -60, "Lid off: board and parts in the back shell")
ax2 = fig.add_subplot(1, 3, 2, projection="3d")
draw(ax2, fp_shapes(), 25, -125, "Assembled, lid see-through", lid_alpha=0.3)
ax3 = fig.add_subplot(1, 3, 3, projection="3d")
draw(ax3, [s for s in shapes_open if "case" not in s[4]], 35, -60, "Board + parts only (case hidden)",
     lims=((96, 128), (-165, -95), (-5, 12)))
plt.tight_layout(); plt.savefig(os.path.join(HERE, "render-3d.png"), dpi=100)
print("rendered render-3d.png")
