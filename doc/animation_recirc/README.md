# Flow animation — one oscillation period

Rendered 2026-08-15 from `runs/p1_trans_q1p25_m0_lam_jet`, Phase 1, isothermal,
`Q` = 1.25 m³/h, laminar, m0 + `--jetRefine`.

**57 frames, t = 48 → 62 s at 0.25 s spacing = 14 s = 1.04 oscillation periods** (the dominant
period is ≈ 13.5 s). Mid-width slice, x = 60 mm. Inlet on the left, outlet on the right.

```
animation.gif        4.8 s at 12 fps
frame_0000.png ...   the individual frames, if you want to re-encode
```

There is no ffmpeg or ImageMagick on this machine, so the GIF is written by Pillow. For a real
video the frames are already PNGs: `ffmpeg -framerate 12 -i frame_%04d.png out.mp4`.

## Two versions, and why

| directory | colour scale | shows |
|---|---|---|
| `doc/animation_jet/` | linear, 0 – 1.3 m/s | why the flow *looks* steady: the jet dominates |
| **`doc/animation_recirc/`** | **clipped, 0 – 0.08 m/s** | **the actual unsteadiness** |

The first version is not a mistake — it is the honest linear picture, and it is worth seeing
first, because it explains the second.

**The jet does not move.** Measured over this exact window:

| probe | mean \|U\| | swing |
|---|---|---|
| jet core | 1.1084 m/s | **0.0 %** |
| mid-chamber, on axis | 1.0990 | 0.1 % |
| off-axis +30 mm | 0.0274 | 32.4 % |
| off-axis −30 mm | 0.0252 | 18.9 % |
| **hood** | 0.0454 | **74.7 %** |

The jet core is steady to four figures. **All of the unsteadiness is in the slow recirculation**,
and it is strongest in the hood. On a linear 0–1.3 m/s ramp that entire signal lives in the
bottom 3 % of the colour range, where nothing is distinguishable — so the linear animation shows
a static picture of a flow that is genuinely moving. Clipping the scale at 0.08 m/s saturates
the jet and gives the recirculation the full ramp.

This also sharpens the language used elsewhere in the project. CLAUDE.md §5.1 describes a
"flapping" confined jet, and that framing came from the steady runs' refusal to converge. What
the transient actually shows is a **steady jet with a slowly wandering recirculation around it**
— which is consistent with the spectrum (100 % of the power below 1 Hz, 0 % in the `St ≈ 0.3`
jet-column band) but is not the same mechanism.

## What to look for in `animation_recirc`

- the **return flow along the hood ceiling**, right to left, changing strength and extent
- the **vortex below the outlet** (bottom right), changing shape
- the **dark corner at bottom left** — inlet end, below the jet, velocity near zero throughout.
  This is the same region the age field puts at ~11 τ (`doc/ventilation/`), so two independent
  measures agree: no flow there, so no air exchange there.

## Caveats

- **Isothermal**, no buoyancy or LED load.
- Faint vertical banding where the `--jetRefine` mesh changes refinement level. It is a
  rendering artefact of the level transition, not flow structure.
- This covers **one period**. The averaging window of the production run is 28.1 s ≈ 2.1
  periods, and the run itself was 6.6 τ; the clip is a window onto the developed flow, resumed
  from t = 48 s with `purgeWrite 0` because the production run's `purgeWrite 5` had kept only
  the last 2 s.
