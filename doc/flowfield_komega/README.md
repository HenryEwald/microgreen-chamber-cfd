# kOmegaSST flow field — stills at t = 48 s

**These are single frames, not an animation.** The laminar arm has a 57-frame animation
(`doc/animation_jet/`, `doc/animation_recirc/`); the kOmegaSST arm cannot have one from the data
that exists. Why, and what it would cost, is at the bottom.

Rendered 2026-08-16 from `runs/p1_trans_q1p25_m0_kom_jet` at t = 48 s (the final write).
Mid-width slice, x = 60 mm. Inlet left, outlet right. `Q` = 1.25 m³/h, m0 + `--jetRefine`,
isothermal.

```
linear/            0 – 1.345 m/s   the honest linear picture: the jet dominates
clipped/           0 – 0.08 m/s    the LAMINAR arm's clip, for direct comparison
clipped_retuned/   0 – 0.14 m/s    re-tuned for this case — read the structure here
```

## The clip has to be re-tuned per case, and that is itself a result

`doc/animation_recirc/` clips at **0.08 m/s**, chosen so the laminar jet saturates and the slow
recirculation gets the full colour ramp. Applied unchanged to the kOmegaSST field, **almost the
entire chamber saturates** — `clipped/` is a wash of yellow with no readable structure.

That is not a rendering mistake, it is the +76 % model spread showing up visually: the RANS
chamber moves ~1.8× faster everywhere, so a threshold set at the laminar recirculation speed is
below most of the RANS field. Re-tuning by the same ratio (0.08 × 1.76 ≈ 0.14) restores
legibility.

Keep both. `clipped/` is the like-for-like comparison against the laminar animation and carries
the finding; `clipped_retuned/` is the one to actually read this case's structure from.

## What `clipped_retuned` shows

Same topology as the laminar arm, which is worth stating plainly — the closure changes the
magnitudes, not the flow pattern:

- the **jet** crossing the chamber from the inlet, spreading as it goes
- the **return flow along the hood ceiling**, right to left
- the **vortex below the outlet**, bottom right
- the **dark dead corner at bottom left** — inlet end, below the jet. Velocity near zero. This is
  the same region the age field puts at its oldest (`doc/ventilation_compare/`), so two
  independent measures agree: no flow there, so no air exchange there.

## Why there is no animation

`system/controlDict` for this case has **`purgeWrite 5`**, which CLAUDE.md §3.3 warns "silently
makes ANIMATION impossible … there is no recovering it afterwards". It did exactly that. The
retained time directories are:

```
41.5  42  42.5  43  43.5        <- 5 frames, 2.0 s
              [ 2.5 s HOLE ]
46    46.5  47   47.5  48       <- 5 frames, 2.0 s
```

Ten frames at 0.5 s spacing, in two clumps separated by a gap, against the laminar arm's **57
contiguous frames at 0.25 s = 14 s ≈ 1.5 recirculation periods**. The longest usable stretch here
is 2 s, which at this arm's 9.35 s period is **0.21 of one cycle** — less than the animation
needs to show anything, and a jump-cut across the hole would be worse than no animation.

The laminar arm avoided this because it was configured `purgeWrite 0`, `writeInterval 0.25`, and
extended to `endTime` 62 s specifically to bank frames.

### What it would take

Restart from t = 48 with `purgeWrite 0` and `writeInterval 0.25`, running to t = 62 to match the
laminar window:

| | |
|---|---|
| simulated time | 14 s (1.5 periods) |
| steps | ~7,140 at Δt 1.96e-3 s |
| measured rate | 1.90 s/step, 8 ranks (from the resumed segment: 2,352 steps in 4,464 s) |
| **wall clock** | **~3.8 h** |
| **disk** | **~12 GB** (the laminar case is 12 GB for 63 time dirs); 70 GB free |

The restart is clean — `48/` holds every `*_0` old-time field and
`uniform/functionObjects/functionObjectProperties`, so it resumes second-order accurate. Only
`endTime`, `writeInterval` and `purgeWrite` need changing, and **`fieldAverage` should be left
alone or given a fresh `timeStart`** if the extension is not to be folded into the reported mean.

⚠ Do **not** re-run `Allrun` to do it — it calls `decomposePar -force` and would destroy the
25 h already spent. Relaunch `mpirun` directly, as in the case's `NOTES.md`.
