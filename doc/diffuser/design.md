# Inlet vane diffuser — design record

**Date:** 2026-08-16
**Status:** geometry + mesh built and verified for all four screen arms. **No solve yet.**

Supersedes nothing; extends CLAUDE.md §6.1/§6.2. Every number here is either measured
from the generated cases or derived from the sources named.

---

## 1. Why

The chamber's Phase 1 answer was that tray-level air is ~0.03 m/s against a 0.3 m/s target,
with ventilation efficiency ε_a ≈ 10 % and severe short-circuiting. Two changes were asked
for: a bigger fan, and a diffuser to fix the distribution.

The scoping question — how much flow is needed — has a clean answer:

| target | delivered Q needed | source |
|---|---|---|
| `U_bulk` = 0.30 m/s | **13.5 m³/h** | `A_free` = 124.8 cm², CLAUDE.md §6.2 |
| `U_bulk` = 0.80 m/s (the ceiling) | 35.9 m³/h | ditto |

**The chamber cannot be over-ventilated.** 35.9 m³/h is far beyond this fan at any port size.
So the only way to exceed the 0.8 m/s ceiling anywhere is a **surviving jet core**, and the
only way to reach 0.3 m/s everywhere is **piston-like flow**. The diffuser's entire job is
converting a jet into a plug. That is the design brief, and it is unusually well posed.

## 2. Operating point

Fan: **Sunon MF50100V2-1000U-A99** — 50 × 50 × 10 mm, 5 VDC, 0.085 A, 430 mW, 4800 rpm,
**11.0 CFM = 18.69 m³/h free air**, **0.110 in-H₂O = 27.4 Pa shut-off**, Vapo-bearing,
25.6 dB(A). ([datasheet](https://www.sunonusa.com/wp-content/uploads/2026/02/MF50100V2-1000U-A99-D05062330G-01-1.pdf),
[DigiKey](https://www.digikey.com/en/products/detail/sunon-fans/MF50100V2-1000U-A99/9863643))

It is a **flow** upgrade, not a **pressure** one — 27.4 Pa is the same class as the LD3007MS it
replaces, because that is what axial fans are. Against a Q² system curve the **port diameter**
therefore does most of the work, since the loss goes as D⁻⁴:

| port Ø | Q [m³/h] | Δp [Pa] | `U_port` [m/s] | `Re_port` | `U_bulk` [m/s] |
|---|---|---|---|---|---|
| 20 (old) | 4.25 | 21.2 | 3.76 | 4 960 | 0.095 |
| 30 | 8.16 | 15.4 | 3.21 | 6 352 | 0.182 |
| **40 (chosen)** | **11.77** | **10.1** | **2.60** | **6 863** | **0.262** |
| 45 | 13.23 | 8.0 | 2.31 | 6 858 | 0.294 |
| 50 | 14.43 | 6.2 | 2.04 | 6 728 | 0.321 |

Three consequences worth stating separately:

1. **`Re_port` ≈ 6 900 — turbulent, not transitional.** `kOmegaSST` is defensible on its own
   terms here, which removes the project's largest error bar (§5.2's 76 % laminar-vs-RANS
   spread on tray mean speed). `Re = 4Q/(πDν)` stays near-constant across port size because
   Q happens to rise roughly linearly with D over this range.
2. **Ø45–50 is better matched to the target than Ø40** on the piston-flow criterion
   (`U_bulk` = 0.294 lands on 0.30 exactly). Ø40 was chosen because it maximises the
   *jet-decay* figure of merit `Q/D`, and it leaves 10 mm of clearance to the hood spring line
   where Ø50 leaves 5 mm. **If the diffuser works, revisit this** — `--portD 45` is a one-word
   change.
3. **The transient is now ~4× cheaper**, ~5 h vs ~20 h per case at m0+`--jetRefine`.
   CLAUDE.md §5.1's "cost is flat in Q" identity assumes a *fixed port*; steps ∝ endTime/Δt ∝
   (1/Q)/(1/U) = U/Q ∝ 1/A, and quadrupling `A_port` raises Q by 9.4× but `U_in` by only 2.35×.

## 3. Diffuser geometry

**Concept: fanned turning-vane cascade.** Originally chosen over a radial cone spreader (which
would throw half its flow into the end wall it is mounted on and up into the hood, already the
stalest volume at 4.87 τ) — **§3a revisits that and keeps a radial arm after all** — and over a
perforated plenum face (theoretically the best uniformity —
it is how wind tunnels make uniform flow — but it eats ~20 % of chamber depth above the tray
and has a 2-D parameter space a 4-case screen cannot resolve). See `concepts.png`.

**Horizontal turning vanes only — there is deliberately no lateral fan.** The lateral spread
needed is 12° (40 → 120 mm over 187 mm), a free jet already opens at ~12° half-angle, and a
wall jet on the tray spreads faster still. Lateral turning buys nothing. Downward tilt buys
the one thing the flow will not do on its own: descend the 41.7 mm to the tray.

| | value |
|---|---|
| vanes | 5, pitch 6.667 mm, spanning the shroud chord at each height |
| chord | 10 mm projected on y (solidity c/s = 1.5) |
| thickness | 1.5 mm — printable at a 0.4 mm nozzle, ~3.6 cells at snappy level 4 |
| camber | circular arc, φ = θ·s; arc length scaled so the y-projected chord is 10 mm **at every tilt**, so the screen does not confound tilt with solidity |
| shroud | Ø41 inner / Ø44 outer, 10 mm long (5.4 % of chamber depth) |
| protrusion | 10 mm into the chamber |
| loss | K ≈ 0.2 on port dynamic head ⇒ **0.8 Pa** of ~17 Pa spare; costs ~1 % of Q |
| θ, downward tilt | **30°** in the revised screen (§3a); the tilt sweep it was originally to anchor was dropped in favour of a concept comparison |

Reaching the tray needs atan(41.7/186.7) = **12.6°**, so 15° grazes it near the far wall,
30° lands at 38 % of depth, 45° at 22 %. **30° is the arm kept**, as the mid-point of that
range and the reference the radial arms are judged against.

The **inlet patch does not move** — it stays the flat disc at y = 0 carrying
`flowRateInletVelocity`, with the vanes downstream inside the fluid. Q remains exactly
specified and no BC changes character.

### Three deliberate embeddings

Coincident surfaces leave snappy's snap direction undefined, and both usual outcomes (a leak,
or a zero-thickness sliver) pass `checkMesh`. So, as for the 1 mm tray oversize in §6.1:

- the shroud rim runs from y = −0.5 mm, **crossing** the end-wall plane rather than ending on it;
- the vane leading edge starts at y = +0.5 mm, out of the inlet patch's plane;
- the vane ends run 0.75 mm past the shroud inner surface, buried in the 1.5 mm shell.

**Consequence: every vane root edge lies inside solid, so `diffuser.eMesh` is deliberately
kept OUT of snappy's `features` list** — exactly as `tray.eMesh` is, and for the same reason.
Explicit feature snapping onto buried edges grows a skirt that is invisible to `Mesh OK` and
shows up only in the total volume. Level-4 `refinementSurfaces` resolves the vanes without it.

`nSurfaceLayers 0` on the vanes: a 1.5 mm plate at 0.417 mm cells cannot carry a 4-layer stack
on both faces. **Vane wall shear is therefore not reportable** — not needed, they are a
flow-turning device, not a heat-transfer surface.

## 3a. Radial (swirl) diffuser — added 2026-08-16 after review

The HVAC ceiling-diffuser form was raised as a candidate. It is **unambiguously better at
mixing** — swirl diffusers are the highest-induction terminal device there is — but mixing is
not the objective, and it has a hard ceiling:

| | ε_a |
|---|---|
| chamber today | 10 % |
| perfect mixing | **50 %** |
| piston flow | **100 %** |

Mixing is a 5× improvement, piston a 10×, and piston also wins on the velocity band because
`U_bulk` = 0.262 m/s means uniform plug flow puts nearly the whole tray in range.

**However**, it exposed a real weakness in the cascade: turning the jet downward does not
**fill the cross-section**. A Ø40 port is 12.6 cm² against 124.8 cm² free area — **10 %**. The
radial form spreads across the whole end wall, which is a route *toward* piston flow, and it
puts flow into the measured dead pocket (inlet side, along the floor, 6.28 τ). So the two
ideas separate cleanly:

- **radial spread** — probably better than the cascade; keep;
- **swirl** — the tangential cant, which converts spread into mixing; the risky part.

### Swirl number and the breakdown threshold

`S = ⅔·tan α·(1−h³)/(1−h²)`, `h` = hub/tip = 0.30. Above `S` ≈ 0.6 swirl breaks down into a
**central recirculation bubble** — in an open room that *is* the mixing mechanism, but in a
closed 2.3 L box it is a standing recirculation, i.e. re-breathing, the same failure as the
short-circuiting it was meant to fix. The chamber is only **4.7 port diameters** long, far
shorter than the 10–20 diameters swirl needs to decay, so whatever is imparted persists.

| vane cant | `S` | regime |
|---|---|---|
| 15° | 0.19 | attached |
| 30° | 0.41 | attached |
| **40°** | **0.60** | **at threshold** |
| 45° | 0.71 | breakdown |
| 55° | 1.02 | strong breakdown |

`make_geometry.py` prints `S` and warns past 0.6.

### Sizing — two things deliberately not copied from the photo

1. **Vane count 12, not 24.** Tangential space per vane is 2πr/N, so at `r` = 6 mm and 40°
   cant, 24 vanes of 1 mm block **83 %** of the hub root. 12 gives 42 % at the root and 13 %
   at the rim.
2. **Cambered, not flat blades.** The flow arrives *axially* from the port, so a flat plate at
   40° would sit at 40° incidence and stall. The camber turns it 0 → α along the chord, as the
   cascade vanes do; only the plane of turning differs.

| | value |
|---|---|
| vanes | 12, hub Ø12 mm, tip Ø41 mm |
| axial extent | 8 mm, held fixed across α so the screen does not confound swirl with solidity |
| thickness | 1.0 mm |
| passage | 3.4 × 14 mm, `Dh` 5.5 mm, `Re` 1033 |
| loss | 2.5–4.9 Pa (K 0.5–1.0) of ~17 Pa spare |

### Revised screen

Concept comparison rather than a tilt sweep:

| case | diffuser | `S` |
|---|---|---|
| `p1d_ctrl_m0` | none | — |
| `p1d_casc30_m0` | cascade, 5 vanes, 30° down | — |
| `p1d_rad15_m0` | radial, 12 vanes, 15° cant | 0.19 |
| `p1d_rad40_m0` | radial, 12 vanes, 40° cant | 0.60 |

This answers *which family* and brackets swirl from nearly-none to the breakdown threshold,
while keeping a directed-flow reference. ~5 h/case, ~20 h total.

## 4. Verification

All four arms, `checkMesh` clean. Total volume against each case's own `V_air`:

| case | cells | total volume [m³] | `V_air` [m³] | deficit |
|---|---|---|---|---|
| `p1d_ctrl_m0` | 382 613 | 2.3292653e-3 | 2.3296085e-3 | **−0.343 mL** |
| `p1d_casc30_m0` | 500 599 | 2.3242740e-3 | 2.3247744e-3 | −0.500 mL |
| `p1d_rad15_m0` | 487 667 | 2.3246981e-3 | 2.3251233e-3 | −0.425 mL |
| `p1d_rad40_m0` | 489 521 | 2.3245871e-3 | 2.3250195e-3 | −0.432 mL |

The control's −0.343 mL is exactly the flush-tray discretisation figure from §6.1. The extra
~0.09-0.16 mL on the diffuser arms is the additional surface discretisation of the vane faces.
**No sealed feature, no skirt** — the domain bounding box is x [0, 0.12], z [0.025, 0.14333],
i.e. the internal width and height exactly, with a 2 µm y overshoot from the shroud embedding.

Surfaces verified closed, oriented and volume-matched to ~1 µL by
`make_geometry.py --verify` before meshing.

## 5. What this does NOT establish

- **No flow has been solved.** Every claim above is geometric or from a 1-D system-curve
  model. Whether the vanes actually deliver tray coverage is the open question, and it is what
  the screen is for.
- **The system curve is an estimate.** `KSYS` = 2.5 is CLAUDE.md §6.2's own figure and the
  fan's mid-curve is a plot image on page 5 of the datasheet, bracketed here between linear
  and quadratic fits. Measure the delivered flow before publishing (§10.2 item 1).
- **The 4-case screen resolves tilt, not concept.** If all four arms disappoint, the answer
  may be that concept C (perforated plenum) was the right family, not that the tilt was wrong.

## 6. Reproducing

```bash
scripts/generate_case.sh --name p1d_ctrl_m0 --mesh m0 --transient --jetRefine
scripts/generate_case.sh --name p1d_casc30_m0 --mesh m0 --transient --jetRefine --diffuser 30
scripts/generate_case.sh --name p1d_rad40_m0  --mesh m0 --transient --jetRefine \
                         --diffuserType radial --diffuser 40
pvpython scripts/render_mesh.py --case runs/p1d_rad40_m0 --out doc/diffuser/mesh_rad40
```

`--Q` is now **solved** from the fan curve against the system curve for the chosen `--portD`;
pass it only to force an operating point off that curve, and the script will say so.
