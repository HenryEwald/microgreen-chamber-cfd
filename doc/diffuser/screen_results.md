# Inlet diffuser concept screen — results

**Date:** 2026-08-19 · **Phase:** 1 (isothermal) · **Mesh:** m0 · **Model:** kOmegaSST
**Fan:** Sunon MF50100V2 on Ø 40 mm ports · **Solver:** `pimpleFoam`, 6.6 τ transient

Four cases, screened against the brief in `design.md` §3a: **turn the inlet jet into a plug**.
The chamber cannot be over-ventilated at this operating point (CLAUDE.md §6.2), so the only
routes above the 0.3–0.8 m/s target band are a surviving jet core, and the only route to
0.3 m/s everywhere is piston-like flow.

---

## 1. Headline table

| | control | cascade 30° | radial 15° | **radial 40°** |
|---|---|---|---|---|
| vanes | none | 5 turning plates | 12 swirl, `S` = 0.19 | 12 swirl, `S` = 0.60 |
| cells | 382,613 | 500,599 | 487,667 | 489,521 |
| `Q` [m³/h] | 11.77 | 11.52 | 11.52 | 11.52 |
| wall clock | 2.77 h | 12.6 h | 8.01 h | 18.1 h |
| **tray mean \|U\| [m/s]** | 0.3040 ± 0.0041 | **1.9985** ± 0.0076 | 0.3837 ± 0.0130 | **0.8970** ± 0.0350 |
| RMS of that [%] | 3.7 | 2.5 | 6.6 | **14.6** |
| **tray CoV** (uniformity) | 0.665 | **0.812** ← worst | 0.712 | **0.528** ← best |
| tray mean, full plane [m/s] | 0.305 | 1.664 | 0.414 | 0.830 |
| **ε_a, ventilation eff. [%]** | 20.1 | 38.8 | 22.3 | **40.6** ← best |
| mean age [τ] | 2.49 | 1.29 | 2.25 | **1.23** |
| hood age [τ] | 2.67 | 1.34 | 2.39 | 1.57 |
| worst cell [τ] | 5.29 | 2.53 | 4.32 | 2.99 |
| domain max \|U\| [m/s] | 3.41 | 6.90 | 5.47 | 5.71 |
| y⁺ area-avg (worst patch) | 1.07 | 3.16 | 2.67 | 3.11 |

Perfect mixing is ε_a = 50 %, piston flow 100 %. Target band for tray speed is **0.3–0.8 m/s**.

## 2. What the screen says

**Radial 40° (`S` = 0.60) is the winner, and it wins on both axes at once** — the best
ventilation effectiveness (40.6 %, double the control) *and* the best uniformity
(CoV 0.528, the only case below the control). Tray mean 0.90 m/s sits just above the 0.8 m/s
top of the band, so if anything it is slightly over-driven rather than under-driven.

**The cascade reaches almost the same ventilation number by the wrong mechanism.** ε_a = 38.8 %
is nearly rad40's, but the tray mean is **2.0 m/s — 2.5× the top of the target band**, and its
uniformity is the *worst* of the four (CoV 0.812, worse than no diffuser at all). The turning
vanes do not fill the cross-section; they aim the jet at the tray. That ventilates well because
an impinging jet entrains well, but it is a scouring jet over the crop, not a plug. **This is
the failure mode `design.md` §3a predicted for a cascade** — "turns the jet without FILLING the
cross-section" — now measured rather than argued.

**Radial 15° barely does anything.** ε_a 22.3 % against the control's 20.1 %, tray mean 0.38
against 0.30. `S` = 0.19 is too little swirl to restructure the flow; it costs 8 h of compute to
move the metrics by roughly one error bar's worth of physical significance.

**All four differences clear their error bars** by ratios of 6 to 197, so nothing here is
sampling noise. That is worth stating explicitly because the error bars are correlated-sample
SEs (`N_eff = N·Δt/2T_int`), not `sd/√N`, which would have overstated confidence ~3–8×.

## 3. The prediction that did NOT hold

`design.md` §3a bracketed radial 40° at `S` = 0.60 as the risky arm: *"`S` > 0.6 gives vortex
breakdown = a standing central recirculation = re-breathing"*, in a chamber only 4.7 port
diameters long against the 10–20 that swirl needs to decay.

**It is the best case in the screen.** Whatever breakdown structure forms, it is mixing the
chamber rather than re-breathing it — worst cell 2.99 τ against the control's 5.29 τ. The
re-breathing concern was reasonable and is not supported by this result.

Two caveats before that is treated as settled. rad40 is also **by far the most unsteady arm**
(tray RMS 14.6 %, against 2.5–6.6 % elsewhere), which is what a wandering breakdown bubble would
look like; and its **hood is relatively the stalest of any case** — 1.57 τ against a bulk of
1.23 τ, i.e. **28 % above its own mean**, where the control's hood is only 7 % above. So rad40
mixes the working volume best while leaving the hood most distinct from it.

## 4. Where the dead air is

The hood is worse than the chamber mean in all four cases, but only mildly (4–7 %) except in
rad40 (28 %). This does **not** reproduce CLAUDE.md §6.1's expectation of a hood that is "the
worst-ventilated region by a wide margin".

**The slice renders show why, and they are the most informative output of the screen:**

| case | what `vent_<case>/02_slice_x.png` shows |
|---|---|
| **control** | A narrow fresh jet running **straight from inlet to outlet**, with stale slabs above and below it at 3–3.6 τ. **Textbook short-circuiting** — the supply air reaches the exhaust without mixing. This, not fan weakness, is why ε_a is 20 %. |
| **cascade 30°** | The jet **deflected sharply down onto the tray**, then sweeping the tray surface to the outlet. Whole chamber much fresher, but a stale pocket remains in the **bottom-left, under the deflected jet**. |
| **radial 15°** | A broadened jet, but recognisably still the control's topology. |
| **radial 40°** | A **broad fresh core** across mid-height, with the stale air confined to **one pocket in the upper-left — the hood on the inlet side**. |

Two things follow. First, the dead air in this chamber pools on the **inlet** side in every
case — beneath or behind the incoming jet — which reproduces the Phase 1 Ø 20 mm finding rather
than the hood-cap expectation. Second, rad40's residual staleness is a **localised pocket**
rather than a diffuse condition, and a pocket is something a geometry change can target.

See `vent_<case>/06_deadvolume.png` for the shape of the worst-ventilated volume in each case.

## 5. Caveats — none of this is publishable yet

1. **The age fields are `upwind`, which is a certified LOWER BOUND on age.** The template's
   `limitedLinear` **failed the exactness identity** on two of four cases (casc30 +3.6 %,
   rad40 +2.3 %, the latter with a max age of 6101 τ — a diverged solve, final linear residual
   8.0e7). `upwind` certifies on all four at |error| ≤ 0.23 %, but `validation/age_of_air.md`
   measures it as reporting the mean **~9 % low**, so every ε_a here is correspondingly
   **biased high**. The bias applies to all four equally, so the *ranking* is robust and the
   *absolute* numbers are optimistic.
2. **The control is not a clean control.** It runs at `Q` = 11.77 m³/h against 11.52 for the
   diffused arms (deliberate — the generator adds `KSYS + 0.2` for a diffuser, so a real
   diffuser costs ~2 % of flow), to `endTime` 4.69 s not 4.82, and it kept only **5 frames**
   because it predates the `purgeWrite 0` change. Its time-averaged fields are valid; its
   animation is not (§6).
3. **Mesh independence is not established at this operating point.** The m0/m1/m2 ladder was
   run at Ø 20 mm / `Q` = 1.25 m³/h. Everything here is m0 at Ø 40 mm / 11.5 m³/h.
4. **y⁺ has left the viscous sublayer on the diffuser arms** — area-average 2.7–3.2 and max
   9–12, i.e. the buffer layer, where CLAUDE.md §7 says wall functions are least reliable. The
   control sits at 1.07. **Do not report diffuser-vane wall shear as resolved.**
5. Isothermal. No LED load, no buoyancy, no canopy. The stable stratification of §6.3 will
   oppose exactly the vertical mixing these diffusers are being credited with.
6. `K_sys` = 2.5 and the fan mid-curve are still estimates — the whole operating point is
   unmeasured (CLAUDE.md §10.2 item 1).

## 6. Deliverables

Per case, in `doc/diffuser/`:

| | |
|---|---|
| `report_<case>.md` | per-case report |
| `anim_<case>_x/animation.gif` | mid-width slice — jet path, hood, tray (the money view) |
| `anim_<case>_z/animation.gif` | port-centreline plan view — inlet → outlet |
| `anim_<case>_{x,z}_log/animation.gif` | the same two views on a **log** scale, 0.007 → 7 m/s |
| `vent_<case>/01..06*.png` | 3D ventilation maps: volume render, three slices, tray plane, dead-volume isosurface |
| `mesh_<case>/` | mesh inspection renders (pre-existing) |

Cross-case: `validation/diffuser_screen_matrix.png`.

**Two animation sets per view, because one scale cannot answer both questions:**

- **Linear, 0 → 0.8 m/s** — 0.8 is the top of the design target band, so the ramp resolves
  exactly the band that matters and *anything saturated is by construction above target*. This
  is the "is the chamber in band?" view. On the fast arms (casc30 at 2.0 m/s, rad40 at 0.9) most
  of the domain saturates, which is the honest answer to that question but destroys the
  structure.
- **Log, 0.007 → 7 m/s** — three decades, resolving the jet and the slow recirculation in the
  same frame. This is the "what is the flow doing?" view, and it exists because the linear set
  hit exactly the failure CLAUDE.md §10.3 records for a linear scale when a fast jet and a slow
  recirculation share a frame.

Keep both; neither substitutes for the other. **All ventilation maps share 0 → 3.0 s.** Every
scale is identical across the four cases — per-case autoscaling would make the same colour mean
a different value in each panel, the trap recorded in CLAUDE.md §10.3.

⚠ **The control's animation is 5 frames** at 0.5 s spacing, against 60 at 0.08 s for the other
three. It shows the flow but cannot show its unsteadiness, and it is not comparable frame-rate
wise. Fixing it means re-running the control (~2.8 h).
