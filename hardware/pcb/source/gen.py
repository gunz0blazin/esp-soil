"""ESP-Soil stake board v1 — generates Gerbers, Excellon drills, previews, DRC.
Design units mm, design origin top-left (y down). Gerber Y = H - y."""
import math, os, zipfile
from PIL import Image, ImageDraw

OUT = "/home/claude/stake-pcb/out"
os.makedirs(OUT, exist_ok=True)
W, H = 24.0, 52.0
NAME = "esp-soil-stake"

# ---------------- components / pads ----------------
# (ref, x, y, net, pad_d, drill, square)
pads = []
def pad(ref, x, y, net, d=1.7, drill=1.0, sq=False):
    pads.append(dict(ref=ref, x=x, y=y, net=net, d=d, drill=drill, sq=sq))

LX, RX = 4.38, 19.62
xiao_left  = ["D0","D1","D2","D3","D4","D5","D6"]
xiao_right = ["5V","GND","3V3","D10","D9","D8","D7"]
net_of = {"D1":"ADC","D4":"SDA","D5":"SCL","GND":"GND","3V3":"3V3"}
for i,(l,r) in enumerate(zip(xiao_left, xiao_right)):
    y = 2.88 + 2.54*i
    pad("U1."+l, LX, y, net_of.get(l, "NC_"+l), sq=(i==0))
    pad("U1."+r, RX, y, net_of.get(r, "NC_"+r))
# AHT10 module header (VIN GND SCL SDA)
for x, n, lab in [(8.19,"3V3","VIN"),(10.73,"GND","GND"),(13.27,"SCL","SCL"),(15.81,"SDA","SDA")]:
    pad("J1."+lab, x, 26.0, n, sq=(lab=="VIN"))
# divider + filter
pad("R1.1", 9.46, 46.50, "PROBE_A", d=1.6, drill=0.8)
pad("R1.2", 9.46, 43.96, "ADC",     d=1.6, drill=0.8)
pad("R2.1", 7.00, 43.96, "ADC",     d=1.6, drill=0.8)
pad("R2.2", 7.00, 46.50, "GND",     d=1.6, drill=0.8)
pad("C1.1", 4.50, 43.96, "ADC",     d=1.6, drill=0.8)
pad("C1.2", 4.50, 46.50, "GND",     d=1.6, drill=0.8)
pad("C2.+", 19.50, 46.50, "3V3",    d=1.6, drill=0.8, sq=True)
pad("C2.-", 19.50, 49.00, "GND",    d=1.6, drill=0.8)
# probe solder pads (A + -)
pad("P1.A",   9.46, 49.5, "PROBE_A", d=1.8)
pad("P1.+",  12.00, 49.5, "3V3",     d=1.8)
pad("P1.-",  14.54, 49.5, "GND",     d=1.8)

holes = [(5.0, 39.5, 2.2), (13.0, 39.5, 2.2)]   # NPTH M2 mounting

# ---------------- traces (top layer) ----------------
traces = []  # (net, width, [pts])
def tr(net, w, *pts): traces.append((net, w, list(pts)))
tr("ADC", 0.4, (LX,5.42), (1.8,5.42), (1.8,43.96), (9.46,43.96))
tr("SDA", 0.4, (LX,13.04), (15.81,13.04), (15.81,26.0))
tr("SCL", 0.4, (LX,15.58), (13.27,15.58), (13.27,26.0))
tr("3V3", 0.6, (RX,7.96), (22.3,7.96), (22.3,29.0), (8.19,29.0), (8.19,26.0))
tr("3V3", 0.6, (22.3,29.0), (22.3,46.5), (12.0,46.5), (12.0,49.5))
tr("PROBE_A", 0.4, (9.46,46.5), (9.46,49.5))

# ---------------- silkscreen font ----------------
P_ = [[(0,0),(0,6),(3,6),(4,5),(4,4),(3,3),(0,3)]]
O_ = [[(1,0),(0,1),(0,5),(1,6),(3,6),(4,5),(4,1),(3,0),(1,0)]]
FONT = {
 "A":[[(0,0),(0,4),(2,6),(4,4),(4,0)],[(0,3),(4,3)]],
 "B":[[(0,0),(0,6),(3,6),(4,5),(4,4),(3,3),(0,3)],[(3,3),(4,2),(4,1),(3,0),(0,0)]],
 "C":[[(4,5),(3,6),(1,6),(0,5),(0,1),(1,0),(3,0),(4,1)]],
 "D":[[(0,0),(0,6),(3,6),(4,5),(4,1),(3,0),(0,0)]],
 "E":[[(4,6),(0,6),(0,0),(4,0)],[(0,3),(3,3)]],
 "G":[[(4,5),(3,6),(1,6),(0,5),(0,1),(1,0),(3,0),(4,1),(4,3),(2,3)]],
 "H":[[(0,0),(0,6)],[(4,0),(4,6)],[(0,3),(4,3)]],
 "I":[[(1,6),(3,6)],[(2,6),(2,0)],[(1,0),(3,0)]],
 "L":[[(0,6),(0,0),(4,0)]],
 "N":[[(0,0),(0,6),(4,0),(4,6)]],
 "O":O_, "P":P_, "R":P_+[[(2,3),(4,0)]],
 "S":[[(4,5),(3,6),(1,6),(0,5),(0,4),(1,3),(3,3),(4,2),(4,1),(3,0),(1,0),(0,1)]],
 "T":[[(0,6),(4,6)],[(2,6),(2,0)]],
 "U":[[(0,6),(0,1),(1,0),(3,0),(4,1),(4,6)]],
 "V":[[(0,6),(2,0),(4,6)]],
 "X":[[(0,0),(4,6)],[(0,6),(4,0)]],
 "0":O_+[[(0,1),(4,5)]],
 "1":[[(1,5),(2,6),(2,0)],[(1,0),(3,0)]],
 "2":[[(0,5),(1,6),(3,6),(4,5),(4,4),(0,0),(4,0)]],
 "3":[[(0,5),(1,6),(3,6),(4,5),(4,4),(3,3),(4,2),(4,1),(3,0),(1,0),(0,1)],[(1,3),(3,3)]],
 "+":[[(0,3),(4,3)],[(2,1),(2,5)]],
 "-":[[(0,3),(4,3)]],
 "^":[[(0,3),(2,6),(4,3)],[(2,6),(2,0)]],
 " ":[],
}
silk = []  # polylines in design coords
def text(s, x, y, h=1.0, center=False, vertical=False):
    k = h/6.0; adv = 5*k
    width = len(s)*adv - k
    if center: x -= width/2
    for i,ch in enumerate(s):
        for stroke in FONT[ch]:
            pts=[]
            for (u,v) in stroke:
                if vertical:   # reads bottom-to-top
                    pts.append((x + (6-v)*k - h, y - (i*adv + u*k)))
                else:
                    pts.append((x + i*adv + u*k, y + h - v*k))
            silk.append(pts)
def rect(x0,y0,x1,y1): silk.append([(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)])

rect(3.25, 0.3, 20.75, 21.0)                 # XIAO body outline
text("XIAO ESP32-C3", 12, 9.5, 1.0, center=True)
text("^ USB-C UP ^", 12, 11.8, 0.9, center=True)
text("AHT10", 12, 22.6, 1.0, center=True)
for x,l in [(8.19,"V"),(10.73,"G"),(13.27,"C"),(15.81,"D")]:
    text(l, x, 27.25, 0.8, center=True)
text("ESP-SOIL V1", 12, 32.6, 1.2, center=True)
text("C1", 4.50, 41.6, 0.9, center=True)
text("R2", 7.00, 41.6, 0.9, center=True)
text("R1", 9.46, 41.6, 0.9, center=True)
rect(16.8, 38.3, 22.2, 45.3); text("C2", 19.5, 41.3, 1.0, center=True)
text("+", 17.6, 45.9, 0.9, center=True)
for x,l in [(9.46,"A"),(12.0,"+"),(14.54,"-")]:
    text(l, x, 47.55, 0.9, center=True)
text("PROBE", 19.0, 50.6, 0.8, center=True)

# ---------------- DRC ----------------
def seg_pt(a,b,p):
    ax,ay=a; bx,by=b; px,py=p
    dx,dy=bx-ax,by-ay; L=dx*dx+dy*dy
    t=0 if L==0 else max(0,min(1,((px-ax)*dx+(py-ay)*dy)/L))
    return math.hypot(ax+t*dx-px, ay+t*dy-py)
def seg_seg(a,b,c,d):
    return min(seg_pt(a,b,c),seg_pt(a,b,d),seg_pt(c,d,a),seg_pt(c,d,b))
CLR = 0.2
errs=[]
segs=[(n,w,p[i],p[i+1]) for n,w,p in traces for i in range(len(p)-1)]
for n,w,a,b in segs:
    for P in pads:
        if P["net"]!=n:
            g=seg_pt(a,b,(P["x"],P["y"]))-w/2-P["d"]/2
            if g<CLR: errs.append(f"trace {n} vs pad {P['ref']}: {g:.3f}")
    for (hx,hy,hd) in holes:
        g=seg_pt(a,b,(hx,hy))-w/2-hd/2
        if g<0.3: errs.append(f"trace {n} vs hole: {g:.3f}")
    for x in (a,b):
        e=min(x[0],W-x[0],x[1],H-x[1])-w/2
        if e<0.3: errs.append(f"trace {n} edge {e:.3f} at {x}")
for i,(n1,w1,a,b) in enumerate(segs):
    for n2,w2,c,d in segs[i+1:]:
        if n1!=n2:
            g=seg_seg(a,b,c,d)-w1/2-w2/2
            if g<CLR: errs.append(f"trace {n1} vs {n2}: {g:.3f}")
for i,P in enumerate(pads):
    for Q in pads[i+1:]:
        g=math.hypot(P["x"]-Q["x"],P["y"]-Q["y"])-P["d"]/2-Q["d"]/2
        if P["net"]!=Q["net"] and g<CLR: errs.append(f"pad {P['ref']} vs {Q['ref']}: {g:.3f}")
    e=min(P["x"],W-P["x"],P["y"],H-P["y"])-P["d"]/2
    if e<0.3: errs.append(f"pad {P['ref']} edge {e:.3f}")
    for (hx,hy,hd) in holes:
        g=math.hypot(P["x"]-hx,P["y"]-hy)-P["d"]/2-hd/2
        if g<0.3: errs.append(f"pad {P['ref']} vs hole {g:.3f}")
# connectivity: every pad on a used net is touched by a trace or is GND (pour)
for P in pads:
    if P["net"].startswith("NC_") or P["net"]=="GND": continue
    hit=any(n==P["net"] and min(math.hypot(q[0]-P["x"],q[1]-P["y"]) for q in pts)<0.01
            or (n==P["net"] and any(seg_pt(pts[i],pts[i+1],(P["x"],P["y"]))<0.01 for i in range(len(pts)-1)))
            for n,w,pts in traces)
    if not hit: errs.append(f"UNCONNECTED pad {P['ref']} ({P['net']})")

# ---------------- Gerber writer ----------------
def fmt(v): return f"{int(round(v*1e6))}"
def XY(x,y): return f"X{fmt(x)}Y{fmt(H-y)}"
class G:
    def __init__(s, fn, func):
        s.fn=fn; s.lines=[f"%TF.FileFunction,{func}*%","%FSLAX46Y46*%","%MOMM*%","%LPD*%","G01*"]
        s.aps={}; s.next=10
    def ap(s, spec):
        if spec not in s.aps:
            s.aps[spec]=s.next; s.lines.insert(4,f"%ADD{s.next}{spec}*%"); s.next+=1
        return s.aps[spec]
    def use(s, spec): s.lines.append(f"D{s.ap(spec)}*")
    def flash(s, spec, x, y): s.use(spec); s.lines.append(XY(x,y)+"D03*")
    def poly(s, spec, pts):
        s.use(spec); s.lines.append(XY(*pts[0])+"D02*")
        for p in pts[1:]: s.lines.append(XY(*p)+"D01*")
    def region(s, pts):
        s.lines.append("G36*"); s.lines.append(XY(*pts[0])+"D02*")
        for p in pts[1:]+[pts[0]]: s.lines.append(XY(*p)+"D01*")
        s.lines.append("G37*")
    def pol(s, dark): s.lines.append("%LPD*%" if dark else "%LPC*%")
    def save(s):
        open(os.path.join(OUT,s.fn),"w").write("\n".join(s.lines+["M02*"])+"\n")
def C(d): return f"C,{d:.3f}"
def R(d): return f"R,{d:.3f}X{d:.3f}"
def padspec(P, grow=0.0): return (R if P["sq"] else C)(P["d"]+grow)

files=[]
# top copper
g=G(f"{NAME}.GTL","Copper,L1,Top")
for P in pads: g.flash(padspec(P),P["x"],P["y"])
for n,w,pts in traces: g.poly(C(w),pts)
g.save(); files.append(g.fn)
# bottom copper: GND pour with thermals
g=G(f"{NAME}.GBL","Copper,L2,Bot")
m=0.5; g.region([(m,m),(W-m,m),(W-m,H-m),(m,H-m)])
g.pol(False)
for P in pads:
    g.flash(C(P["d"]+0.8), P["x"],P["y"])
for hx,hy,hd in holes: g.flash(C(hd+1.0),hx,hy)
g.pol(True)
for P in pads:
    g.flash(padspec(P),P["x"],P["y"])
    if P["net"]=="GND":
        r=P["d"]/2+0.45
        for dx,dy in [(r,0),(-r,0),(0,r),(0,-r)]:
            g.poly(C(0.5),[(P["x"],P["y"]),(P["x"]+dx,P["y"]+dy)])
g.save(); files.append(g.fn)
# masks
for fn,func in [(f"{NAME}.GTS","Soldermask,Top"),(f"{NAME}.GBS","Soldermask,Bot")]:
    g=G(fn,func)
    for P in pads: g.flash(padspec(P,0.1),P["x"],P["y"])
    g.save(); files.append(fn)
# silkscreen top
g=G(f"{NAME}.GTO","Legend,Top")
for pts in silk: g.poly(C(0.15),pts)
g.save(); files.append(g.fn)
# outline
g=G(f"{NAME}.GKO","Profile,NP")
g.poly(C(0.1),[(0,0),(W,0),(W,H),(0,H),(0,0)])
g.save(); files.append(g.fn)
# drills
def drill(fn, items, plated):
    tools={}
    for d,x,y in items: tools.setdefault(round(d,3),[]).append((x,y))
    L=["M48","; ESP-Soil stake v1","FMAT,2","METRIC,TZ",f"; {'PLATED' if plated else 'NON_PLATED'}"]
    for i,d in enumerate(sorted(tools),1): L.append(f"T{i}C{d:.3f}")
    L+=["%","G90","G05"]
    for i,d in enumerate(sorted(tools),1):
        L.append(f"T{i}")
        for x,y in tools[d]: L.append(f"X{x:.3f}Y{H-y:.3f}")
    L+=["T0","M30"]
    open(os.path.join(OUT,fn),"w").write("\n".join(L)+"\n")
drill(f"{NAME}-PTH.DRL",[(P["drill"],P["x"],P["y"]) for P in pads],True); files.append(f"{NAME}-PTH.DRL")
drill(f"{NAME}-NPTH.DRL",[(d,x,y) for x,y,d in holes],False); files.append(f"{NAME}-NPTH.DRL")
with zipfile.ZipFile(os.path.join(OUT,f"{NAME}-gerbers.zip"),"w") as z:
    for f in files: z.write(os.path.join(OUT,f),f)

# ---------------- previews ----------------
S=24; pad_px=40
def px(x,y): return (pad_px+x*S, pad_px+y*S)
def render(side):
    im=Image.new("RGB",(int(W*S+2*pad_px),int(H*S+2*pad_px)),(245,245,245))
    d=ImageDraw.Draw(im)
    d.rectangle([px(0,0),px(W,H)],fill=(22,90,50))
    if side=="bottom":
        d.rectangle([px(0.5,0.5),px(W-0.5,H-0.5)],fill=(40,120,70))
        for P in pads:
            r=(P["d"]+0.8)/2*S; cx,cy=px(P["x"],P["y"]); d.ellipse([cx-r,cy-r,cx+r,cy+r],fill=(22,90,50))
        for hx,hy,hd in holes:
            r=(hd+1.0)/2*S; cx,cy=px(hx,hy); d.ellipse([cx-r,cy-r,cx+r,cy+r],fill=(22,90,50))
        for P in pads:
            if P["net"]=="GND":
                cx,cy=px(P["x"],P["y"]); r=(P["d"]/2+0.45)*S
                d.line([cx-r,cy,cx+r,cy],fill=(40,120,70),width=int(0.5*S)); d.line([cx,cy-r,cx,cy+r],fill=(40,120,70),width=int(0.5*S))
    else:
        for n,w,pts in traces:
            d.line([px(*p) for p in pts],fill=(200,150,60),width=int(w*S),joint="curve")
    for P in pads:
        cx,cy=px(P["x"],P["y"]); r=P["d"]/2*S
        box=[cx-r,cy-r,cx+r,cy+r]
        (d.rectangle if P["sq"] else d.ellipse)(box,fill=(215,180,90))
        r2=P["drill"]/2*S; d.ellipse([cx-r2,cy-r2,cx+r2,cy+r2],fill=(30,30,30))
    for hx,hy,hd in holes:
        cx,cy=px(hx,hy); r=hd/2*S; d.ellipse([cx-r,cy-r,cx+r,cy+r],fill=(30,30,30))
    if side=="top":
        for pts in silk: d.line([px(*p) for p in pts],fill=(255,255,255),width=max(2,int(0.15*S)))
    im=im if side=="top" else im.transpose(Image.FLIP_LEFT_RIGHT)
    im.save(os.path.join(OUT,f"preview-{side}.png"))
render("top"); render("bottom")

print("DRC:", "PASS" if not errs else f"{len(errs)} issues")
for e in errs: print("  ",e)
print("files:", files)
