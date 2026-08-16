# Ventilation map — laminar vs kOmegaSST, on **one shared colour scale**

Rendered 2026-08-16 from the two Phase 1 transient arms, `Q` = 1.25 m³/h, m0 + `--jetRefine`,
isothermal, identical mesh and BCs. Only `constant/turbulenceProperties` differs.

```
laminar/   runs/p1_trans_q1p25_m0_lam_jet   age on phiMean at t = 62 s
komega/    runs/p1_trans_q1p25_m0_kom_jet   age on phiMean at t = 48 s
```

Both sets carry **the same six panels and the same colour range, 0 – 77.05 s (0 – 10.57 τ)**,
τ = 7.2866 s. That is the whole point of this directory.

## Why a shared scale, and why it needed a new flag

`render_field.py` auto-scales to each case's own data range. Rendered that way the two sets come
out **0 – 77.05 s** (laminar) and **0 – 49.15 s** (kOmegaSST), so *the same colour means a
different age in each directory* — 25 s is mid-magenta in one and dark purple in the other. Put
side by side they mislead in the direction of the conclusion, which is the worst case.

This is exactly the `AutomaticRescaleRangeMode` trap CLAUDE.md §10.3 records for panels *within*
one render, occurring one level up: between documents instead of between panels. The fix is the
same — pin the range. `render_field.py --range 0 77.05` was added for this.

The per-case auto-scaled version of the kOmegaSST set is kept separately in
`doc/ventilation_komega/`, because it is the more legible picture of *that case on its own*. Use
this directory for any laminar-vs-RANS comparison; use that one to read the RANS field's internal
structure.

## The result

| | laminar | kOmegaSST |
|---|---|---|
| volume-mean age | 36.15 s = **4.96 τ** | 13.28 s = **1.82 τ** |
| worst cell | 77.04 s = 10.57 τ | 49.15 s = 6.75 τ |
| dead-volume threshold (1.5× mean) | 54.2 s = 7.44 τ | 19.9 s = 2.73 τ |
| **ventilation efficiency ε_a** | **10.1 %** | **27.4 %** |

On the shared scale the kOmegaSST chamber is visibly, uniformly darker — it reports air **2.7×
fresher** everywhere. That is the over-diffusion artefact reaching the headline design metric:
CLAUDE.md §5.2 measured `ν_t` = 5× molecular at `Re_port` = 1458, i.e. `Re_eff` = 242. The RANS
arm is mixing a chamber that is not turbulent.

**The laminar arm is the physically defensible one here.** These figures exist to show how much
the closure moves a design conclusion — 10 % vs 27 % is "short-circuits badly, needs a port
redesign" against "mediocre but workable" — not to offer a choice between two answers.

Both age solves are certified by the mass-conservation identity `<age>_outlet ≡ τ`:
**−0.045 %** (laminar) and **−0.046 %** (kOmegaSST). See `validation/age_of_air.md`.

## Panels

| file | what |
|---|---|
| `01_volume.png` | volume render — where the stale air is, in 3D |
| `02_slice_x.png` | mid-width cut, x = 60 mm — hood, jet, tray |
| `03_slice_y.png` | mid-depth cut, y = 93.3 mm |
| `04_slice_z.png` | port-centreline cut, z = 66.7 mm — the inlet → outlet path |
| `05_tray_plane.png` | the metric surface, z = 30 mm over the tray |
| `06_deadvolume.png` | isosurface at 1.5× the volume mean — **note the threshold differs per case**, so this is the one panel that is *not* directly comparable |

## Caveats

- **Slotted-tray geometry.** Both cases predate the 2026-08-16 flush-tray redesign: `V_air`
  2.5300828e-3 m³, τ 7.29 s, tray metric area 0.0141697 m². Not comparable with anything
  generated after that date (CLAUDE.md §6.1).
- **Isothermal.** No buoyancy, no LED load. Phase 2 adds a stable stratification that will
  *suppress* vertical mixing further (CLAUDE.md §6.3), so these are optimistic.
- **`Q` = 1.25 m³/h is a placeholder** pending the LD3007MS Δp–Q curve.
- The kOmegaSST arm is less converged in time than the laminar one (`N_eff` 6.3 vs 15.0, mean
  still drifting −0.7 % past the discard). Worth ~1 %; it does not move the 2.7× gap. See
  `validation/transient_matrix.md` §4e.
