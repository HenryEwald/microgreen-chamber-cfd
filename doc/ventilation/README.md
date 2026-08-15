# 3D ventilation map — mean age of air

Rendered 2026-08-15 from `runs/p1_trans_q1p25_m0_lam_jet`, Phase 1, isothermal,
`Q` = 1.25 m³/h, laminar, m0 + `--jetRefine`.

The field is **mean age of air** computed on `phiMean` — the *time-averaged* flux over 3.85 τ
of a 6.6 τ transient, not a snapshot. Regenerate with:

```bash
scripts/age_of_air.sh runs/p1_trans_q1p25_m0_lam_jet
pvpython scripts/render_field.py --case runs/p1_trans_q1p25_m0_lam_jet/ageEval \
    --field age --time 48.00000001 --out doc/ventilation
```

## The numbers behind the pictures

| | value | × τ |
|---|---|---|
| volume mean | 36.39 s | **4.99** |
| hood zone | 35.52 s | 4.87 |
| canopy zone | 34.72 s | 4.76 |
| worst cell | 82.05 s | 11.26 |
| **outlet (identity check)** | **7.2832 s** | **0.9995** ✓ |
| **air exchange efficiency ε_a** | **10.0 %** | (50 % = perfect mixing) |

τ = V_air/Q = 7.286 s. `ageOutlet` must equal τ for any steady flow — it does, to
**−0.047 %**, which is what certifies the transport solve converged.

## The panels

| file | what it shows |
|---|---|
| `01_volume.png` | volume render — the whole field in 3D, hood vault and port visible |
| `02_slice_x.png` | mid-width cut (x = 60 mm) — **the clearest single image**: the jet as a dark band, everything above and below stale |
| `03_slice_y.png` | mid-depth cut (y = 93.3 mm) |
| `04_slice_z.png` | port-centreline cut (z = 66.7 mm) — the inlet → outlet path |
| `05_tray_plane.png` | the metric surface, z = 30 mm over the tray |
| `06_deadvolume.png` | cells with age > 1.5× the volume mean (54.6 s = 7.5 τ), over a translucent chamber outline |

## What they show

**The chamber short-circuits.** In `02_slice_x` the jet runs as a near-black (age ≈ 0) band
straight from inlet to outlet at port height, and everything above and below it sits at
30–70 s. Fresh air crosses the chamber and leaves without mixing into the bulk.

**The dead volume is at crop level, not in the hood.** `06_deadvolume` shows the worst-
ventilated air as a slab along the **floor**, wrapping up the end walls, with a channel
scooped out of it where the jet's entrainment reaches down. That is agronomically the worst
possible place for it — the tray sits in it.

This is the second, independent refutation of CLAUDE.md §6.1's prediction that the hood would
be "the worst-ventilated region by a wide margin". The zone averages already said the hood is
at 0.976 of the chamber mean; the pictures say the stale air is *below* the jet, not above it.

**The dead air is on the INLET side, not the outlet side** — measured, not read off the
pictures. Volume-averaged age in slabs across the chamber depth (inlet at y = 0, outlet at
y = 186.7 mm; patch bounds verified, not inferred):

| distance from inlet | mean age | × τ |
|---|---|---|
| **0–23 mm (inlet)** | **45.8 s** | **6.28** |
| 47–70 mm | 37.4 s | 5.14 |
| 93–117 mm | 35.7 s | 4.89 |
| 140–163 mm | 31.8 s | 4.36 |
| **163–187 mm (outlet)** | **28.9 s** | **3.96** |

Air is **58 % older at the inlet end than at the outlet end**, falling monotonically across all
eight slabs. Counterintuitive but mechanistically clear: the jet entrains as it crosses, so
everything downstream is progressively swept toward the exit, while the pocket *beneath the
incoming jet* sits in its shadow — too fast to exchange with, and with no return flow bringing
fresh air back upstream. The worst cell (~11 τ) is in that inlet-end floor corner.

**Consequence for the design.** The tray spans y = 30.8–155.8 mm, i.e. the whole gradient, so
the crop sees ~6.3 τ air at the inlet end and ~4.0 τ at the outlet end — a **~55 % variation in
air age across the tray**, on top of the overall ε_a ≈ 10 %.

This also changes which fix is indicated. A hood dead zone would argue for aiming the jet
upward. An inlet-end floor pocket argues for changes to the **port arrangement** — angling the
inlet downward, offsetting the ports diagonally instead of face-to-face, or providing a return
path — none of which is a jet-strength problem.

## Colour

Sequential, perceptually uniform (Inferno), dark = fresh → bright = stale, **one shared scale
(0–82 s) across all six panels**. Not a rainbow: rainbow maps invent banding where a field is
smooth and flatten it where it is steep, which disqualifies them for a field whose entire
content is where the gradients are.

> Two rendering defects were found and fixed by looking at the output rather than trusting it:
> ParaView's default `AutomaticRescaleRangeMode` gave **every panel its own scale** (the x-slice
> came out −0.12…76, the tray plane 21…68 — same field, same instant), and the dead-volume panel
> was originally a `Contour`, which draws the *shell* of the region as a sheet floating in space
> with nothing to locate it against. It is now a `Threshold` over a translucent boundary.

## Caveats

- **Isothermal.** No buoyancy, no LED load. Phase 2 would add a `T` map; at the current 38.4 W
  placeholder its temperatures would be non-physical (§6.3), though the stratification *pattern*
  would still be informative.
- `Q` = 1.25 m³/h is a **motivated placeholder**, not a measurement — the LD3007MS Δp–Q curve is
  still outstanding (§10.2). Every age here scales with it.
- The laminar closure is the defensible one at `Re_port` = 1458, but the kOmegaSST arm gives a
  tray mean **~110 % higher**; it will produce its own, more optimistic, age map when it
  finishes.
