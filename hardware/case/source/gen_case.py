"""ESP-Soil stake case v2 (snap-fit) — back shell + lid for the 24x52 mm stake PCB + SEN0193 probe.
Edit the parameters, run `python3 gen_case.py`, get STLs + an OpenSCAD file + previews.
Frame: x across width, y along length (y=0 = top/USB end), z up from the back face. mm."""
import numpy as np, struct, os, zipfile
from skimage.measure import marching_cubes
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)

# ---------------- parameters ----------------
pcb_w, pcb_l, pcb_t = 24.0, 52.0, 1.6
clr        = 0.4    # side clearance around the PCB
wall       = 1.8
floor_t    = 1.6    # back
lid_t      = 1.6
back_clear = 3.0    # room for solder joints under the PCB
front_clear= 9.5    # XIAO on headers is ~8 mm tall; AHT10 module similar
top_gap    = 0.5    # PCB top edge to inside of the top wall
gap        = 3.0    # carrier bottom edge to probe top edge (solder leads)
probe_w, probe_t = 23.0, 1.6
probe_in   = 30.0   # length of probe (its electronics end) kept inside the case
usb_w, usb_z0 = 13.0, 7.5   # USB-C plug opening width; bottom of opening above back face
holes = [(5.0, 39.5), (13.0, 39.5)]   # PCB mounting holes (PCB coords)
res = 0.2           # STL resolution
# snap-fit latches: cantilever arms hang from the lid inside the long walls, hooks click into wall windows
use_screws = False  # True = v1-style M2 screws as well (lid bosses get holes, standoffs get pilots)
snap_y   = None     # latch centres along y (case frame); None = auto (near USB end, below AHT10, probe end)
arm_w    = 6.0      # latch arm width (along y)
arm_t    = 1.2      # arm thickness (flex direction). Thicker = stiffer
arm_len  = 8.0      # arm length below the lid plate. Longer = easier to snap
hook_h   = 0.8      # how far the hook sticks out into the wall window (engagement)
hook_ramp= 1.6      # lead-in ramp height on the hook
snap_clr = 0.2      # clearance around hook in the window

# ---------------- derived ----------------
in_w = pcb_w + 2*clr
in_l = top_gap + pcb_l + gap + probe_in
in_d = back_clear + pcb_t + front_clear
W, L = in_w + 2*wall, in_l + 2*wall
Hs   = floor_t + in_d               # back-shell height (open front)
X0, Y0 = wall + clr, wall + top_gap # PCB origin in case frame
Zb = floor_t + back_clear           # PCB bottom
Zt = Zb + pcb_t                     # PCB top
Yp = Y0 + pcb_l + gap               # probe top edge
Xp = W/2 - probe_w/2

# ---------------- CSG ----------------
def box(x0,y0,z0,x1,y1,z1): return ("box",(x0,y0,z0,x1,y1,z1))
def cyl(cx,cy,z0,z1,d):     return ("cyl",(cx,cy,z0,z1,d))
def xzpoly(pts,y0,y1):      return ("xzpoly",(tuple(pts),y0,y1))   # convex polygon in x-z, extruded along y
back_ops, lid_ops = [], []   # ordered CSG: ('+'|'-', primitive)
class _L(list):
    def __init__(s, ops, sign): s.ops, s.sign = ops, sign
    def append(s, p): s.ops.append((s.sign, p))
    def __iadd__(s, ps):
        for p in ps: s.append(p)
        return s
back_add, back_sub = _L(back_ops,'+'), _L(back_ops,'-')
lid_add,  lid_sub  = _L(lid_ops,'+'),  _L(lid_ops,'-')

# back shell
back_add.append(box(0,0,0,W,L,Hs))
back_sub.append(box(wall,wall,floor_t,W-wall,L-wall,Hs+1))
# PCB edge ledges (carrier region)
for xa,xb in [(wall, X0+0.6),(W-wall-clr-0.6, W-wall)]:
    back_add.append(box(xa, Y0, floor_t, xb, Y0+pcb_l, Zb))
# probe rails (probe region)
for xa,xb in [(wall, Xp+0.8),(Xp+probe_w-0.8, W-wall)]:
    back_add.append(box(xa, Yp, floor_t, xb, L-wall, Zb))
# standoffs: M2 pilot holes (screw option) or locating pins through the PCB holes (snap version)
for hx,hy in holes:
    back_add.append(cyl(X0+hx, Y0+hy, floor_t-0.01, Zb, 4.6))
    if use_screws: back_sub.append(cyl(X0+hx, Y0+hy, floor_t-1.0, Zb+0.1, 1.7))
    else:          back_add.append(cyl(X0+hx, Y0+hy, Zb-0.01, Zt+1.0, 1.9))
# USB-C notch (open to the front rim; lid closes the top)
back_sub.append(box(W/2-usb_w/2, -1, usb_z0, W/2+usb_w/2, wall+0.1, Hs+1))
# probe slot through bottom wall
back_sub.append(box(Xp-0.2, L-wall-0.1, Zb-0.2, Xp+probe_w+0.2, L+1, Zt+0.2))
# side vents beside the AHT10 (PCB y 24..38)
for k in range(5):
    y = Y0 + 25 + k*3
    for xa,xb in [(-1, wall+0.1),(W-wall-0.1, W+1)]:
        back_sub.append(box(xa, y, Zt+1.0, xb, y+1.4, Hs-1.0))

# lid (case frame: sits on the rim, z = Hs .. Hs+lid_t)
lid_add.append(box(0,0,Hs,W,L,Hs+lid_t))
# locating lip inside the walls (gap at the USB notch)
lt, ld, g = 1.2, 2.0, 0.25
xi0, xi1, yi0, yi1 = wall+g, W-wall-g, wall+g, L-wall-g
lid_add += [box(xi0,yi0,Hs-ld,xi0+lt,yi1,Hs), box(xi1-lt,yi0,Hs-ld,xi1,yi1,Hs),
            box(xi0,yi1-lt,Hs-ld,xi1,yi1,Hs),
            box(xi0,yi0,Hs-ld,W/2-usb_w/2-0.5,yi0+lt,Hs), box(W/2+usb_w/2+0.5,yi0,Hs-ld,xi1,yi0+lt,Hs)]
# heat baffle between XIAO and AHT10 (stops 1 mm above the PCB)
lid_add.append(box(xi0, Y0+22.0, Zt+1.0, xi1, Y0+23.0, Hs))
# bosses down to the PCB top (clamp PCB onto standoffs)
for hx,hy in holes:
    lid_add.append(cyl(X0+hx, Y0+hy, Zt, Hs, 4.6))
    if use_screws:
        lid_sub.append(cyl(X0+hx, Y0+hy, Zt-1, Hs+lid_t+1, 2.4))
        lid_sub.append(cyl(X0+hx, Y0+hy, Hs+lid_t-1.2, Hs+lid_t+1, 4.2))   # counterbore
    else:
        lid_sub.append(cyl(X0+hx, Y0+hy, Zt-1, Zt+1.6, 2.4))   # socket for the locating pin
# probe clamp ribs (press probe edges onto rails)
for xa,xb in [(xi0, Xp+0.8),(Xp+probe_w-0.8, xi1)]:
    lid_add.append(box(xa, Yp+2, Zt+0.1, xb, yi1, Hs))
# top vents over the AHT10
for k in range(5):
    y = Y0 + 25 + k*3
    lid_sub.append(box(X0+3, y, Hs-1, X0+pcb_w-3, y+1.4, Hs+lid_t+1))

# snap latches (added last so nothing above cuts them)
if snap_y is None: snap_y = [Y0+8.0, Y0+46.0, Yp+18.0]
za = Hs - arm_len                 # arm tip
zc = za + hook_ramp               # hook catch face
assert za > Zt + 1.0, "latch arm would hit the PCB parts; shorten arm_len"
for yc in snap_y:
    ya, yb = yc-arm_w/2, yc+arm_w/2
    for side in (0,1):
        # free the arm: cut the lip / clamp rib around it (not the plate)
        if side==0: lid_sub.append(box(xi0-0.1, ya-0.6, Zt-1, xi0+arm_t+1.2, yb+0.6, Hs-0.01))
        else:       lid_sub.append(box(xi1-arm_t-1.2, ya-0.6, Zt-1, xi1+0.1, yb+0.6, Hs-0.01))
for yc in snap_y:
    ya, yb = yc-arm_w/2, yc+arm_w/2
    for side in (0,1):
        xo = xi0 if side==0 else xi1               # outer face of the arm (faces the wall)
        sg = -1 if side==0 else 1                  # direction toward the wall
        xin = xo - sg*arm_t
        lid_add.append(box(min(xo,xin), ya, za, max(xo,xin), yb, Hs))
        lid_add.append(xzpoly([(xo, za), (xo, zc), (xo+sg*hook_h, zc), (xo+sg*hook_h, zc-0.3)], ya, yb))
        # matching window through the back-shell wall
        wx0, wx1 = (-1, wall+0.1) if side==0 else (W-wall-0.1, W+1)
        back_sub.append(box(wx0, ya-snap_clr, za-0.4, wx1, yb+snap_clr, zc+snap_clr))

# ---------------- voxelise + STL ----------------
def voxel(ops, zlo, zhi):
    nx, ny, nz = int(np.ceil(W/res))+1, int(np.ceil(L/res))+1, int(np.ceil((zhi-zlo)/res))+1
    xs = (np.arange(nx)+0.5)*res; ys=(np.arange(ny)+0.5)*res; zs=zlo+(np.arange(nz)+0.5)*res
    X,Y,Z = np.meshgrid(xs,ys,zs,indexing="ij")
    v = np.zeros((nx,ny,nz),bool)
    def mask(p):
        k,a = p
        if k=="box":
            x0,y0,z0,x1,y1,z1=a; return (X>=x0)&(X<=x1)&(Y>=y0)&(Y<=y1)&(Z>=z0)&(Z<=z1)
        if k=="xzpoly":
            pts,y0,y1=a; n=len(pts); m=(Y>=y0)&(Y<=y1)
            cr=[(pts[(i+1)%n][0]-pts[i][0])*(Z-pts[i][1])-(pts[(i+1)%n][1]-pts[i][1])*(X-pts[i][0]) for i in range(n)]
            return m&(np.all([c>=0 for c in cr],0)|np.all([c<=0 for c in cr],0))
        cx,cy,z0,z1,d=a; return ((X-cx)**2+(Y-cy)**2<=(d/2)**2)&(Z>=z0)&(Z<=z1)
    for sg,p in ops:
        if sg=='+': v|=mask(p)
        else: v&=~mask(p)
    return v, zlo
def write_3mf(verts, faces, fn):
    """3MF = zipped mesh, ~6x smaller than STL; every major slicer opens it."""
    vx="".join(f'<vertex x="{a:.3f}" y="{b:.3f}" z="{c:.3f}"/>' for a,b,c in verts)
    tr="".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a,b,c in faces)
    model=('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
           f'<object id="1" type="model"><mesh><vertices>{vx}</vertices><triangles>{tr}</triangles></mesh></object>'
           '</resources><build><item objectid="1"/></build></model>')
    with zipfile.ZipFile(os.path.join(OUT,fn),"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        z.writestr("[Content_Types].xml",'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels",'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model",model)
def write_stl(v, zlo, fn, flip_z_top=None):
    pad=np.pad(v,1).astype(np.float32)
    verts,faces,_,_=marching_cubes(pad,0.5,spacing=(res,res,res))
    verts-=res; verts[:,2]+=zlo
    if flip_z_top is not None:
        verts[:,2]=flip_z_top-verts[:,2]; faces=faces[:,::-1]
    verts[:,2]-=verts[:,2].min()
    vol=np.einsum("ij,ij->i",verts[faces[:,0]],np.cross(verts[faces[:,1]],verts[faces[:,2]])).sum()/6
    if vol<0: faces=faces[:,::-1]          # outward-facing winding
    write_3mf(verts,faces,fn.replace(".stl",".3mf"))
    tri=verts[faces]; n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    n/= (np.linalg.norm(n,axis=1,keepdims=True)+1e-12)
    with open(os.path.join(OUT,fn),"wb") as f:
        f.write(b"ESP-Soil stake case".ljust(80,b" ")); f.write(struct.pack("<I",len(faces)))
        data=np.zeros(len(faces),dtype=[("n","<f4",3),("v","<f4",(3,3)),("a","<u2")])
        data["n"]=n; data["v"]=tri; f.write(data.tobytes())
    return len(faces)
vb,zb=voxel(back_ops,0,Hs)
vl,zl=voxel(lid_ops,Zt-0.2,Hs+lid_t)
nb=write_stl(vb,zb,"stake-case-back.stl")
nl=write_stl(vl,zl,"stake-case-lid.stl",flip_z_top=Hs+lid_t)   # outer face on the bed

# ---------------- OpenSCAD (same primitives) ----------------
def scad(p):
    k,a=p
    if k=="box":
        x0,y0,z0,x1,y1,z1=a; return f"translate([{x0:.3f},{y0:.3f},{z0:.3f}]) cube([{x1-x0:.3f},{y1-y0:.3f},{z1-z0:.3f}]);"
    if k=="xzpoly":
        pts,y0,y1=a; P=",".join(f"[{x:.3f},{z:.3f}]" for x,z in pts)
        return f"multmatrix([[1,0,0,0],[0,0,1,{y0:.3f}],[0,1,0,0],[0,0,0,1]]) linear_extrude(height={y1-y0:.3f}) polygon([{P}]);"
    cx,cy,z0,z1,d=a; return f"translate([{cx:.3f},{cy:.3f},{z0:.3f}]) cylinder(d={d:.3f},h={z1-z0:.3f},$fn=48);"
def scad_ops(ops):
    expr = scad(ops[0][1])
    for sg,p in ops[1:]:
        expr = ("union(){\n" if sg=='+' else "difference(){\n") + expr + "\n" + scad(p) + "\n}"
    return expr
with open(os.path.join(OUT,"stake-case.scad"),"w") as f:
    f.write("// ESP-Soil stake case v2 (snap-fit) - generated by gen_case.py (edit parameters there and re-run)\n")
    f.write(f"// Outer: {W:.1f} x {L:.1f} x {Hs+lid_t:.1f} mm. part = \"back\" | \"lid\" | \"both\"\npart=\"both\";\n")
    f.write("module back(){\n"+scad_ops(back_ops)+"\n}\n")
    f.write("module lid(){\n"+scad_ops(lid_ops)+"\n}\n")
    f.write(f"if(part==\"back\") back();\nelse if(part==\"lid\") translate([0,0,{Hs+lid_t:.3f}]) mirror([0,0,1]) lid();\nelse {{ back(); translate([0,0,15]) lid(); }}\n")

np.savez_compressed(os.path.join(OUT,"_vox.npz"),vb=vb,vl=vl,zl=zl)
print(f"Outer {W:.1f} x {L:.1f} x {Hs+lid_t:.1f} mm | back {nb} tris | lid {nl} tris")
print(f"PCB z {Zb:.1f}-{Zt:.1f}, probe top at y={Yp:.1f}, case bottom y={L:.1f}, probe inside {probe_in} mm")
print(f"Latches at y={[round(y,1) for y in snap_y]} both sides; arm tip z={za:.1f}, catch z={zc:.1f}")
if use_screws: print(f"Screw length ~ {lid_t+ (Hs-Zt) + pcb_t + back_clear + 1.0:.1f} mm (M2 self-tapping)")
