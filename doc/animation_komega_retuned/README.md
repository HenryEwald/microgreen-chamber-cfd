# kOmegaSST flow animation — and why it shows almost nothing

Rendered 2026-08-16 from `runs/p1_trans_q1p25_m0_kom_jet`, Phase 1, isothermal,
`Q` = 1.25 m³/h, kOmegaSST, m0 + `--jetRefine`.

**39 frames, t = 48 → 57.5 s at 0.25 s spacing = 9.5 s = 1.0 oscillation period** (this arm's
dominant period is 9.35 s). Mid-width slice, x = 60 mm. Inlet left, outlet right. Same view,
frame rate and encoder as the laminar `doc/animation_recirc/`.

```
animation.gif        3.2 s at 12 fps
frame_0000.png ...   39 individual frames
```

Two versions, both from the same data:

| directory | clip | purpose |
|---|---|---|
| `doc/animation_komega_recirc/` | **0.08 m/s** — the laminar arm's clip | like-for-like against `doc/animation_recirc/`; **saturates** |
| **`doc/animation_komega_retuned/`** | **0.14 m/s** | legible — read this one |

The laminar clip saturates here because the RANS chamber moves ~1.8× faster everywhere (the
+76 % model spread, `validation/transient_matrix.md` §4e). Re-tuning by the same ratio
(0.08 × 1.76 ≈ 0.14) restores contrast. The saturated version is kept because that saturation
*is* the finding, not a rendering mistake.

## ⚠ The animation is nearly static, and that is a RESULT

Measured over the chamber region of the rendered frames, against the laminar animation:

| | mean pixel range | p99 | max frame-to-frame |
|---|---|---|---|
| `doc/animation_recirc/` (laminar) | **13.03** / 255 | 85.0 | 72 |
| `doc/animation_komega_retuned/` | **0.23** / 255 | 2.0 | 9 |

**~52× less visible motion.** Nothing is wrong with the render — the colour scale is pinned,
the frames are contiguous, and the same pipeline produced the laminar animation. The RANS flow
is simply not moving by this point in the record.

### Why: this arm is relaxing to a STEADY state

Sliding a one-period window along the record and measuring fluctuation amplitude
(`validation/plot_fluctuation_decay.py`) separates a sustained oscillation from a decaying
transient. The two arms behave oppositely:

| arm | probe | first window | last window | ratio |
|---|---|---|---|---|
| laminar | hood | 9.96 % | 11.16 % | **1.12 — sustained** |
| laminar | off-axis −30 | 4.00 % | 4.19 % | **1.05 — sustained** |
| **kOmegaSST** | hood | 1.48 % | **0.05 %** | **0.03 — decaying** |
| **kOmegaSST** | off-axis −30 | 12.62 % | **0.36 %** | **0.03 — decaying** |

The kOmegaSST fluctuation falls ~30× monotonically across six successive windows while the
laminar one is flat. **The animated window sits at the far end of that decay**, where the RANS
flow has essentially arrived at steady state — so there is genuinely nothing left to animate.

This is consistent with CLAUDE.md §5.2: at `ν_t` = 5× molecular the effective Reynolds number is
242, not 1458, and a flow at `Re` = 242 in this geometry is steady. It is also why the *steady*
kOmegaSST run converged 2.4 orders where every laminar steady run stalled.

See `validation/transient_matrix.md` §4f for the full argument and its caveats — including why
this is **different evidence** from the claim §4a retracted, not a re-derivation of it.

## What to look for anyway

The structure is the same as the laminar arm — the closure changes magnitudes, not topology:

- the **jet** crossing from the inlet, spreading as it goes
- the **return flow along the hood ceiling**, right to left
- the **vortex below the outlet**, bottom right
- the **dark dead corner at bottom left** — inlet end, below the jet, near-zero velocity. The
  age field independently puts this region at its oldest (`doc/ventilation_compare/`).

## Caveats

- **Slotted-tray geometry** (pre-2026-08-16): `V_air` 2.5300828e-3 m³, τ 7.2866 s. Not
  comparable with anything generated after the flush-tray redesign.
- **Isothermal.** No buoyancy, no LED load.
- **`Q` = 1.25 m³/h is a placeholder** pending the LD3007MS Δp–Q curve.
- **These frames are NOT in the reported time average.** The run was extended 48.11 → 57.5 s
  purely to bank them; the statistics in §4e are frozen at 48.11 s. See the case `NOTES.md`.
- One period is a short record. The *decay* conclusion above does not rest on it — that uses the
  full 20.05 → 57.5 s window, ~4 cycles.
