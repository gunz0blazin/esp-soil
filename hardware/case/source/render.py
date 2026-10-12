import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
exec(open("gen_case.py").read().split("# ---------------- voxelise")[0])
d=np.load("out/_vox.npz"); vb,vl,zl=d["vb"],d["vl"],float(d["zl"])
def shade(h):
    gx,gy=np.gradient(h); n=np.dstack([-gx,-gy,np.full_like(h,0.6)])
    n/=np.linalg.norm(n,axis=2,keepdims=True); l=np.array([-0.5,-0.6,0.62]); l/=np.linalg.norm(l)
    return np.clip(0.25+0.75*(n@l),0,1)
def heightmap(v, top=True):
    nz=v.shape[2]
    if top: h=np.where(v.any(2), nz-1-np.argmax(v[:,:,::-1],axis=2), -5)
    else:   h=np.where(v.any(2), np.argmax(v,axis=2), nz+5)
    return h.astype(float)*res
fig,ax=plt.subplots(1,5,figsize=(19,9.5),gridspec_kw={"width_ratios":[1,1,1.25,1.25,0.9]})
ext=[0,W,L,0]
hb=heightmap(vb,True)
a=ax[0]; a.imshow(shade(hb).T,cmap="copper",extent=ext)
a.add_patch(Rectangle((X0,Y0),pcb_w,pcb_l,fill=False,ec="lime",lw=1.4,ls="--"))
a.add_patch(Rectangle((Xp,Yp),probe_w,L-Yp+6,fill=False,ec="cyan",lw=1.4,ls="--"))
a.set_title("BACK SHELL from front\nledges, standoffs, rails\ngreen=PCB  cyan=probe",fontsize=9); a.set_ylim(L+7,-2)
hl=-heightmap(vl,False)
a=ax[1]; a.imshow(shade(hl).T,cmap="bone",extent=ext)
a.add_patch(Rectangle((X0+4,Y0+26),16,11,fill=False,ec="magenta",lw=1.2))
a.add_patch(Rectangle((X0+3.25,Y0+0.3),17.5,20.7,fill=False,ec="orange",lw=1.2))
a.set_title("LID inside face\nlip, baffle, bosses, clamp ribs\norange=XIAO  magenta=AHT10",fontsize=9)
for yc in snap_y:
    for a_,c in ((ax[0],"red"),(ax[1],"red")):
        a_.add_patch(Rectangle((0,yc-arm_w/2),W,arm_w,fill=False,ec=c,lw=1,ls=":"))
# cross-section through a latch pair (x-z at y = snap_y[1])
iy=int(snap_y[1]/res)
sec=vb[:,iy,:].astype(float)
nzt=int(np.ceil((Hs+lid_t)/res))+2; S=np.zeros((vb.shape[0],nzt)); S[:,:sec.shape[1]]=sec*0.8
off=int(round(zl/res)); ls_=vl[:,iy,:]; S[:,off:off+ls_.shape[1]]=np.maximum(S[:,off:off+ls_.shape[1]],ls_*0.5)
a=ax[2]; a.imshow(1-S.T,cmap="Greys_r",origin="lower",extent=[0,W,0,nzt*res],vmin=0,vmax=1)
a.add_patch(Rectangle((X0,Zb),pcb_w,pcb_t,color="green",alpha=0.8))
a.add_patch(Rectangle((X0+3.25,Zt),17.5,1e-3,color="orange"))
a.set_title(f"SECTION through latches (y={snap_y[1]:.1f})\ndark=back  mid=lid  green=PCB",fontsize=9)
S_latch=S.copy()
# section through top wall (USB) at y = wall/2
iy=int((wall/2)/res); sec=vb[:,iy,:].astype(float)
S=np.zeros((vb.shape[0],nzt)); S[:,:sec.shape[1]]=sec*0.8
ls_=vl[:,iy,:]; S[:,off:off+ls_.shape[1]]=np.maximum(S[:,off:off+ls_.shape[1]],ls_*0.5)
a=ax[3]; a.imshow(1-S.T,cmap="Greys_r",origin="lower",extent=[0,W,0,nzt*res],vmin=0,vmax=1)
a.add_patch(Rectangle((W/2-4.5,Zt+2.5+1.0),9,3.2,fill=False,ec="orange",lw=1.6))
a.add_patch(Rectangle((W/2-6.2,Zt+2.5+1.0+1.6-3.3),12.4,6.6,fill=False,ec="red",lw=1,ls=":"))
a.set_title("TOP END wall (USB-C)\norange=receptacle  red=typical plug body",fontsize=9)
a=ax[4]; a.imshow(1-S_latch.T,cmap="Greys_r",origin="lower",extent=[0,W,0,nzt*res],vmin=0,vmax=1,interpolation="nearest")
a.set_xlim(-0.5,5); a.set_ylim(5,Hs+lid_t+0.5); a.set_aspect("equal")
a.set_title("LATCH close-up (left)\nhook clicks into wall window\npush hook in through window to open",fontsize=9)
for a in ax: a.tick_params(labelsize=7)
plt.tight_layout(); plt.savefig("out/preview.png",dpi=105)
