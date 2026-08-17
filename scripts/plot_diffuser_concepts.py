import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyArrow
import numpy as np

W, D, BOXH, TRAY = 120., 186.667, 96.667, 25.
PZ, PX, PR = 66.667, 60., 20.          # port centre z, x and NEW radius (O40)

FLOW = "#1f77b4"; VANE = "#c0392b"; SOLID = "#8c8c8c"; TRAYC = "#4a7c1f"

def chamber_plan(ax):
    ax.add_patch(Rectangle((0,0), W, D, fc="#f4f4f0", ec="k", lw=1.4))
    ax.plot([PX-PR, PX+PR],[0,0], color=FLOW, lw=4, solid_capstyle="butt")
    ax.plot([PX-PR, PX+PR],[D,D], color="#d35400", lw=4, solid_capstyle="butt")
    ax.text(PX, -9, "inlet Ø40", ha="center", va="top", fontsize=7, color=FLOW)
    ax.text(PX, D+8, "outlet Ø40", ha="center", va="bottom", fontsize=7, color="#d35400")
    ax.set_xlim(-14, W+14); ax.set_ylim(-20, D+20); ax.set_aspect("equal"); ax.axis("off")

def chamber_side(ax):
    ax.add_patch(Rectangle((0,0), D, BOXH, fc="#f4f4f0", ec="k", lw=1.4))
    ax.add_patch(Rectangle((0,0), D, TRAY, fc=TRAYC, ec="k", lw=1.0, alpha=.55))
    ax.text(D/2, TRAY/2, "TRAY  (metric surface, z = 25 mm)", ha="center", va="center",
            fontsize=6.5, color="w", weight="bold")
    ax.plot([0,0],[PZ-PR, PZ+PR], color=FLOW, lw=4, solid_capstyle="butt")
    ax.plot([D,D],[PZ-PR, PZ+PR], color="#d35400", lw=4, solid_capstyle="butt")
    ax.set_xlim(-22, D+16); ax.set_ylim(-12, BOXH+14); ax.set_aspect("equal"); ax.axis("off")

def arrows(ax, pts, dirs, L, c=FLOW, w=1.3):
    for (x,y),(dx,dy) in zip(pts, dirs):
        n = np.hypot(dx,dy)
        ax.arrow(x, y, dx/n*L, dy/n*L, head_width=4.2, head_length=5.5,
                 fc=c, ec=c, lw=w, length_includes_head=True)

fig, axes = plt.subplots(2, 3, figsize=(15.5, 8.4))
fig.suptitle("Inlet diffuser concepts — Ø40 mm port, Sunon MF50100V2, Q ≈ 11.8 m³/h",
             fontsize=13, weight="bold", y=0.985)

# ---------------- A: radial cone / swirl spreader ----------------
ax = axes[0,0]; chamber_plan(ax); ax.set_title("A  Radial cone spreader", fontsize=10, weight="bold")
for a in np.linspace(-80, 80, 9):
    r = np.deg2rad(a); ax.arrow(PX, 2, np.sin(r)*46, np.cos(r)*46, head_width=3.6,
        head_length=4.6, fc=FLOW, ec=FLOW, lw=1.0, length_includes_head=True, alpha=.75)
ax.add_patch(Circle((PX,0), PR*0.55, fc=VANE, ec="k", lw=.8, alpha=.9))
ax.text(2, D*0.80, "360° spread:\nhalf the flow hits\nthe end wall + hood", fontsize=7.5, va="top")

ax = axes[1,0]; chamber_side(ax)
for a in np.linspace(-55, 55, 7):
    r = np.deg2rad(a); dx, dz = np.cos(r), np.sin(r)
    L = 44.
    if dz > 0: L = min(L, (BOXH-4-PZ)/dz)
    if dz < 0: L = min(L, (TRAY+3-PZ)/dz)
    ax.arrow(3, PZ, dx*L, dz*L, head_width=3.4,
        head_length=4.4, fc=FLOW, ec=FLOW, lw=1.0, length_includes_head=True, alpha=.75)
ax.text(D*0.46, BOXH*0.80, "much of it aimed UP\ninto the hood dead volume", fontsize=7.5, color="#a33")

# ---------------- B: fanned turning-vane cascade ----------------
ax = axes[0,1]; chamber_plan(ax); ax.set_title("B  Fanned turning-vane cascade  ← recommended",
                                               fontsize=10, weight="bold", color="#1a6")
for a in (-15,-7.5,0,7.5,15):
    r = np.deg2rad(a)
    x0 = PX + a/15*PR*0.8
    ax.plot([x0, x0+np.sin(r)*16],[1, 1+np.cos(r)*16], color=VANE, lw=2.6, solid_capstyle="round")
for a in np.linspace(-15,15,5):
    r = np.deg2rad(a); x0 = PX + a/15*PR*0.8
    ax.arrow(x0+np.sin(r)*18, 1+np.cos(r)*18, np.sin(r)*120, np.cos(r)*120,
             head_width=4.0, head_length=5.2, fc=FLOW, ec=FLOW, lw=1.1,
             length_includes_head=True, alpha=.8)
ax.text(2, D*0.86, "±15° lateral is enough:\na free jet already spreads\n~12°, and 40→120 mm over\n187 mm needs only 12°",
        fontsize=7.2, va="top")

ax = axes[1,1]; chamber_side(ax)
for a in (0,-8,-16,-24):
    r = np.deg2rad(a); z0 = PZ + a/24*PR*0.7
    ax.plot([1, 1+np.cos(r)*16],[z0, z0+np.sin(r)*16], color=VANE, lw=2.6, solid_capstyle="round")
for a in np.linspace(-24,0,4):
    r = np.deg2rad(a); z0 = PZ + a/24*PR*0.7
    x0, dx, dz = 1+np.cos(r)*18, np.cos(r), np.sin(r)
    L = min((D-6-x0)/dx, (TRAY+2.5-z0-np.sin(r)*18)/dz if dz < 0 else 1e9)
    ax.arrow(x0, z0+np.sin(r)*18, dx*L, dz*L,
             head_width=3.6, head_length=4.8, fc=FLOW, ec=FLOW, lw=1.1,
             length_includes_head=True, alpha=.8)
ax.annotate("", xy=(D*0.75, TRAY+3), xytext=(D*0.75, PZ-8),
            arrowprops=dict(arrowstyle="<->", color="#333", lw=1.0))
ax.text(D*0.77, (TRAY+PZ)/2, "41.7 mm\nto tray", fontsize=6.8, va="center")
ax.text(D*0.06, BOXH*0.90, "downward tilt is THE parameter\n(lateral spread is nearly free)",
        fontsize=7.5, color="#1a6", weight="bold")

# ---------------- C: perforated plenum ----------------
ax = axes[0,2]; chamber_plan(ax); ax.set_title("C  Perforated plenum face", fontsize=10, weight="bold")
ax.add_patch(Rectangle((6,0), W-12, 13, fc=SOLID, ec="k", lw=.9, alpha=.75))
for x in np.linspace(12, W-12, 13):
    ax.add_patch(Circle((x, 13), 2.0, fc="w", ec="k", lw=.5))
    ax.arrow(x, 16, 0, 40, head_width=3.4, head_length=4.4, fc=FLOW, ec=FLOW,
             lw=.9, length_includes_head=True, alpha=.8)
ax.text(2, D*0.86, "best uniformity in principle\n(wind-tunnel settling screen);\nplenum eats ~20 % of chamber depth", fontsize=7.2, va="top")

ax = axes[1,2]; chamber_side(ax)
ax.add_patch(Rectangle((0,TRAY+4), 13, BOXH-TRAY-10, fc=SOLID, ec="k", lw=.9, alpha=.75))
for z in np.linspace(TRAY+10, BOXH-10, 7):
    ax.add_patch(Circle((13, z), 2.0, fc="w", ec="k", lw=.5))
    ax.arrow(16, z, 42, 0, head_width=3.2, head_length=4.2, fc=FLOW, ec=FLOW,
             lw=.9, length_includes_head=True, alpha=.8)
ax.text(D*0.26, BOXH*0.90, "loss acts on the 0.54 m/s FACE velocity:\nonly 1.6–3.4 Pa at σ = 0.3–0.4 — affordable.\nReal cost is chamber VOLUME + printability",
        fontsize=7.0, color="#555", weight="bold")

for ax, t in zip(axes[0], ["PLAN (x–y), looking down"]*3): ax.set_ylabel(t)
axes[0,0].text(-0.06, .5, "PLAN\n(looking down)", transform=axes[0,0].transAxes,
               rotation=90, va="center", ha="center", fontsize=8, weight="bold")
axes[1,0].text(-0.06, .5, "SIDE\n(y–z at x=60)", transform=axes[1,0].transAxes,
               rotation=90, va="center", ha="center", fontsize=8, weight="bold")
plt.tight_layout(rect=[0.01,0.01,1,0.96])
plt.savefig("doc/diffuser/concepts.png", dpi=135)
print("wrote doc/diffuser/concepts.png")
