from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors as C
W,H=letter
c=canvas.Canvas("/home/claude/stake-pcb/out/esp-soil-stake-build.pdf",pagesize=letter)
c.setTitle("ESP-Soil Stake v1")
BLK=C.HexColor("#222222"); GREY=C.HexColor("#666666"); RED=C.HexColor("#c0392b")
BLUE=C.HexColor("#1f6fb2"); GRN=C.HexColor("#2e8b57"); ORG=C.HexColor("#d68910")
def title(t,s):
    c.setFillColor(BLK); c.setFont("Helvetica-Bold",18); c.drawString(40,H-50,t)
    c.setFont("Helvetica",9.5); c.setFillColor(GREY); c.drawString(40,H-65,s); c.setFillColor(BLK)
def notes(x,y,lines,size=9.5,lead=13.5):
    for ln in lines:
        if ln.startswith("#"):
            y-=4; c.setFont("Helvetica-Bold",size+1.5); c.drawString(x,y,ln[1:]); y-=lead+1
        else:
            c.setFont("Helvetica",size); c.drawString(x,y,ln); y-=lead
    return y
def box(x,y,w,h,label,sub=None):
    c.setStrokeColor(BLK); c.setFillColor(C.HexColor("#eef2f5")); c.setLineWidth(1)
    c.roundRect(x,y,w,h,5,fill=1); c.setFillColor(BLK); c.setFont("Helvetica-Bold",10)
    c.drawCentredString(x+w/2,y+h+6,label)
    if sub: c.setFont("Helvetica",8); c.setFillColor(GREY); c.drawCentredString(x+w/2,y-12,sub); c.setFillColor(BLK)
def pin(x,y,name,side,col=BLK):
    c.setFont("Helvetica",8); c.setFillColor(col)
    if side=="r": c.drawRightString(x-4,y-3,name)
    else: c.drawString(x+4,y-3,name)
    c.setFillColor(BLK); c.circle(x,y,1.8,fill=1)
def wire(pts,col):
    c.setStrokeColor(col); c.setLineWidth(1.6); p=c.beginPath(); p.moveTo(*pts[0])
    for q in pts[1:]: p.lineTo(*q)
    c.drawPath(p); c.setFillColor(col)
    for q in (pts[0],pts[-1]): c.circle(*q,2.2,fill=1)
def gnd(x,y):
    c.setStrokeColor(BLK); c.setLineWidth(1.2); c.line(x,y,x,y-8)
    for i,w in enumerate((8,5,2)): c.line(x-w,y-8-i*3,x+w,y-8-i*3)
def vcc(x,y):
    c.setStrokeColor(RED); c.setLineWidth(1.2); c.line(x,y,x,y+8); c.line(x-6,y+8,x+6,y+8)
    c.setFillColor(RED); c.setFont("Helvetica-Bold",7.5); c.drawCentredString(x,y+11,"3V3"); c.setFillColor(BLK)
def res(x,y,horiz,label,val):
    c.setStrokeColor(BLK); c.setLineWidth(1.2)
    if horiz: c.rect(x-14,y-5,28,10)
    else: c.rect(x-5,y-14,10,28)
    c.setFont("Helvetica-Bold",8); c.drawString(x+(18 if not horiz else -10),y+(2 if not horiz else 9),label)
    c.setFont("Helvetica",7.5); c.drawString(x+(18 if not horiz else -10),y+(-8 if not horiz else -16),val)
def cap(x,y,label,val,pol=False):
    c.setStrokeColor(BLK); c.setLineWidth(1.4)
    c.line(x-8,y+2,x+8,y+2); c.line(x-8,y-2,x+8,y-2)
    c.setFont("Helvetica-Bold",8); c.drawString(x+11,y+2,label); c.setFont("Helvetica",7.5); c.drawString(x+11,y-8,val)
    if pol: c.setFont("Helvetica",7); c.drawString(x-14,y+4,"+")

# ---------------- page 1: schematic ----------------
title("ESP-Soil Stake v1 — Schematic","One stake per pot: XIAO ESP32-C3 + AHT10 + SEN0193 probe. USB-C power, Wi-Fi to Prometheus/Grafana.")
# XIAO block
bx,by,bw,bh=240,430,130,190
box(bx,by,bw,bh,"U1  XIAO ESP32-C3","USB-C = power in")
L=["D0","D1 / GPIO3","D2","D3","D4 / GPIO6","D5 / GPIO7","D6"]; R=["5V","GND","3V3","D10","D9","D8","D7"]
lp={};rp={}
for i,(l,r) in enumerate(zip(L,R)):
    y=by+bh-22-i*24
    pin(bx,y,l,"l"); lp[l]=(bx,y); pin(bx+bw,y,r,"r"); rp[r]=(bx+bw,y)
# AHT10
ax,ay=470,500; box(ax,ay,90,80,"J1  AHT10 module","temp / humidity")
ap={}
for i,n in enumerate(["VIN","GND","SCL","SDA"]):
    y=ay+68-i*18; pin(ax,y,n,"l"); ap[n]=(ax,y)
# probe
px_,py_=60,190; box(px_,py_,90,70,"P1  SEN0193 probe","solder pads A / + / -")
pp={}
for i,n in enumerate(["A","+","-"]):
    y=py_+55-i*20; pin(px_+90,y,n,"r"); pp[n]=(px_+90,y)
# wires
wire([lp["D4 / GPIO6"],(200,lp["D4 / GPIO6"][1]),(200,660),(430,660),(430,ap["SDA"][1]),ap["SDA"]],GRN)
c.setFillColor(GRN); c.setFont("Helvetica-Bold",8); c.drawString(300,664,"SDA"); 
wire([lp["D5 / GPIO7"],(210,lp["D5 / GPIO7"][1]),(210,650),(440,650),(440,ap["SCL"][1]),ap["SCL"]],ORG)
c.setFillColor(ORG); c.drawString(300,640,"SCL")
# 3V3 / GND of xiao
wire([rp["3V3"],(395,rp["3V3"][1])],RED); vcc(395,rp["3V3"][1])
wire([rp["GND"],(420,rp["GND"][1]),(420,rp["GND"][1]-6)],BLK); gnd(420,rp["GND"][1]-6)
wire([ap["VIN"],(455,ap["VIN"][1])],RED); vcc(455,ap["VIN"][1])
wire([ap["GND"],(450,ap["GND"][1]),(450,ap["GND"][1]-10)],BLK); gnd(450,ap["GND"][1]-10)
c.setFillColor(GREY); c.setFont("Helvetica",7.5); c.drawString(470,470,"I2C pull-ups are on the AHT10 module")
# C2 bulk
cap(520,420,"C2","100 uF 6.3V+",pol=True); vcc(520,432); c.setStrokeColor(BLK); c.line(520,422,520,432); c.line(520,418,520,404); gnd(520,404)
# probe chain: A -> R1 -> ADC node -> D1 ; R2 & C1 to gnd
yA=pp["A"][1]
wire([pp["A"],(200,yA)],BLUE); res(214,yA,True,"R1","10k")
wire([(228,yA),(300,yA)],BLUE)
c.setFillColor(BLUE); c.setFont("Helvetica-Bold",8); c.drawString(250,yA+6,"ADC")
res(300,yA-30,False,"R2","33k"); c.setStrokeColor(BLUE); c.line(300,yA,300,yA-16); c.setStrokeColor(BLK); c.line(300,yA-44,300,yA-52); gnd(300,yA-52)
cap(360,yA-30,"C1","0.1 uF"); c.setStrokeColor(BLUE); c.line(300,yA,360,yA); c.line(360,yA,360,yA-28); c.setStrokeColor(BLK); c.line(360,yA-32,360,yA-52); gnd(360,yA-52)
wire([(360,yA),(420,yA),(420,400),(190,400),(190,lp["D1 / GPIO3"][1]),lp["D1 / GPIO3"]],BLUE)
wire([pp["+"],(170,pp["+"][1])],RED); vcc(170,pp["+"][1])
wire([pp["-"],(175,pp["-"][1]),(175,pp["-"][1]-8)],BLK); gnd(175,pp["-"][1]-8)
notes(40,140,[
"#Why the divider (R1/R2)",
"The ESP32-C3's ADC tops out around 2.5 V. A dry SEN0193 can sit right at that, so R1/R2 scale it by 0.767",
"(2.5 V -> 1.92 V, 1.2 V -> 0.92 V). Calibration uses the voltage at the ESP pin, so nothing else changes.",
"Don't want it? Fit a wire link in R1 and leave R2 empty.",
"#Nets",
"ADC: P1.A -> R1 -> D1/GPIO3 (R2 + C1 to GND)    SDA: D4/GPIO6    SCL: D5/GPIO7    3V3: XIAO 3V3 -> AHT VIN, P1 +, C2",
])
c.showPage()

# ---------------- page 2: board + stake ----------------
title("Board Layout and Stake Assembly","24 x 52 mm, 2-layer, 1.6 mm. Top: all signals. Bottom: solid ground pour.")
c.drawImage("/home/claude/stake-pcb/out/preview-top.png",40,250,width=180,height=180*1328/656)
c.drawImage("/home/claude/stake-pcb/out/preview-bottom.png",235,250,width=180,height=180*1328/656)
c.setFont("Helvetica-Bold",10); c.drawCentredString(130,240,"TOP"); c.drawCentredString(325,240,"BOTTOM (mirrored view)")
# stake side view
sx=470; c.setFont("Helvetica-Bold",10); c.drawString(440,700,"Stake side view")
# case
c.setFillColor(C.HexColor("#cfd8dc")); c.setStrokeColor(GREY); c.roundRect(sx-22,520,44,150,6,fill=1)
c.setFillColor(BLK); c.setFont("Helvetica",7.5); c.drawString(sx+28,640,"printed case")
c.drawString(sx+28,630,"(vents near AHT10)")
# usb
c.setFillColor(C.HexColor("#888888")); c.rect(sx-6,670,12,8,fill=1); c.setFillColor(BLK); c.drawString(sx+28,672,"USB-C power out the top")
# board
c.setFillColor(C.HexColor("#165a32")); c.rect(sx-4,535,8,130,fill=1)
c.setFillColor(BLK); c.drawString(sx+28,600,"stake PCB (52 mm)")
# probe
c.setFillColor(C.HexColor("#1b2631")); c.rect(sx-4,330,8,205,fill=1)
c.drawString(sx+28,450,"SEN0193 probe")
c.drawString(sx+28,440,"(wired to A / + / -)")
# soil
c.setStrokeColor(C.HexColor("#6e4b2a")); c.setLineWidth(2); c.line(sx-60,480,sx+60,480)
c.setFillColor(C.HexColor("#6e4b2a")); c.drawString(sx-60,485,"soil surface")
c.setStrokeColor(RED); c.setLineWidth(1); c.setDash(3,2); c.line(sx-30,500,sx+30,500); c.setDash()
c.setFillColor(RED); c.drawString(sx-60,504,"probe's max line")
c.setFillColor(BLK)
notes(440,300,[
"#Seal it",
"Case must seal at the probe",
"(silicone or a gland). Only the",
"probe below its line goes in soil.",
"Conformal-coat the probe's",
"electronics and this board.",
],size=8.5,lead=11.5)
notes(40,215,[
"#Mechanical",
"Board 24 x 52 mm, same width as the SEN0193. USB-C sits at the top edge (y = 0). Two M2 holes 8 mm apart",
"at 39.5 mm down for screwing the board to the case. Tallest parts: XIAO on headers (~8 mm) and the AHT10 module.",
"Lay C2 (electrolytic) flat over its outline. Keep the AHT10 near case vents and away from the XIAO for honest readings.",
"#Order it",
"Upload esp-soil-stake-gerbers.zip to JLCPCB or PCBWay: 2 layers, 1.6 mm, HASL. Defaults are fine; check the",
"preview in their viewer before paying. 5 boards is usually a few dollars plus shipping.",
])
c.showPage()

# ---------------- page 3: BOM + build ----------------
title("BOM, Assembly and Calibration","All through-hole. Hand-solderable.")
rows=[("Ref","Part","Qty/board","Notes"),
("U1","Seeed XIAO ESP32-C3","1","Solder on 1x7 male headers (or flush)"),
("J1","AHT10 module (VIN GND SCL SDA)","1","Check your module's pin order matches V G C D"),
("P1","DFRobot SEN0193 probe","1","Remove its JST plug, wire 3 short leads to A + -"),
("R1","10k resistor, 1/4W","1","Or a wire link to skip the divider"),
("R2","33k resistor, 1/4W","1","Leave empty if R1 is a link"),
("C1","0.1 uF ceramic, 2.54 mm","1","ADC noise filter"),
("C2","100 uF 6.3V+ electrolytic, 2.5 mm","1","Lay flat, + to square pad"),
("—","2x 1x7 female headers (optional)","1","Lets you unplug the XIAO; adds height"),
("—","2x M2 screws","2","Mount to case")]
y=H-100; cols=[40,80,270,340]
for i,r in enumerate(rows):
    c.setFont("Helvetica-Bold" if i==0 else "Helvetica",9)
    if i==0: c.setFillColor(C.HexColor("#d5dbdb")); c.rect(35,y-4,W-70,15,fill=1,stroke=0); c.setFillColor(BLK)
    for x,t in zip(cols,r): c.drawString(x,y,t)
    y-=16
notes(40,y-10,[
"#Assembly order",
"1. Solder R1, R2, C1 first (lowest parts), then C2 bent flat.",
"2. Power test the bare board: plug nothing in, check for shorts with a meter (3V3-GND, 5V-GND should NOT beep).",
"3. Solder the AHT10 header and module.",
"4. Solder the XIAO last. Square pad = D0 (top left), USB-C toward the top edge.",
"5. Wire the probe: A = signal (blue), + = 3V3 (red), - = GND (black). Keep leads short.",
"6. Flash soil-stake.yaml over USB (change plant / node_name per stake), then mount in the case.",
"#Calibration (per stake)",
"Watch 'Plant N raw' in Grafana/HA/logs. This is the voltage at the ESP pin, after the divider.",
"dry_v = probe in air or bone-dry mix.  wet_v = 30 min after watering to runoff. Put both in the YAML and reflash.",
"#Grafana",
"Add each stake's IP:80 to prometheus.yml. Sensors are named 'Plant N moisture / temperature / humidity / leaf VPD',",
"so the existing dashboard picks them up. Give each stake a fixed IP in UniFi.",
"#Heads-up",
"The AHT10 now sits at soil level, not canopy height, so expect warmer/more humid readings than at the canopy.",
"The ESP warms the board slightly; compare against a trusted thermometer once and set the offset in the YAML.",
"Unverified: this layout was generated without KiCad, so check the Gerbers in JLCPCB's viewer and measure your",
"XIAO and AHT10 against the footprint (XIAO rows 15.24 mm apart, 2.54 mm pitch) before ordering.",
])
c.save()
