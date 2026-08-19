# p1d_rad15_m0 — radial swirl, 12 vanes at 15° (`S` = 0.19)

Twelve radial vanes on a Ø 12 mm hub, tilted 15°. The **attached-swirl** arm: swirl number
`S` = 0.19, well below the ~0.6 vortex-breakdown threshold.

| | |
|---|---|
| solver / model | `pimpleFoam`, kOmegaSST, isothermal |
| mesh | m0 + level-4 on the vanes, **487,667** cells |
| `Q` | 11.52 m³/h |
| τ | 0.7279 s · endTime 4.82 s = 6.6 τ |
| Δt | 1.26e-4 s — `maxCo` bound |
| wall clock | **8.01 h**, ~38,000 steps |
| frames | 60 |

## Result

| metric | value | vs control |
|---|---|---|
| tray mean \|U\| | **0.3837 ± 0.0130 m/s** (RMS 6.6 %) | +26 % |
| tray CoV | 0.712 | **worse** (0.665) |
| ventilation ε_a | 22.3 % | +2.2 pts (20.1 %) |
| mean age | 2.25 τ | 2.49 τ |
| hood age | 2.39 τ (1.06× the mean) | |
| worst cell | 4.32 τ | 5.29 τ |
| domain max \|U\| | 5.47 m/s = 2.15 × `U_in` | 3.41 |

**`S` = 0.19 is not enough swirl to restructure this chamber.** Every metric moves in the right
direction and none of them moves far: ε_a goes from 20.1 % to 22.3 %, the worst cell from 5.29
to 4.32 τ, tray speed from 0.30 to 0.38 m/s. The differences clear their error bars — this is a
real effect, not noise — but it is a small effect bought with 8 h of compute and a diffuser in
the bore.

**Uniformity actually got worse** (CoV 0.665 → 0.712), which is the interesting part: the
attached swirl adds azimuthal structure over the tray without adding enough radial spread to
even it out. So the low-swirl concept is not simply "the winner but weaker" — it is a different,
mildly worse, flow topology.

Set against its sibling at 40° (`S` = 0.60, ε_a 40.6 %, CoV 0.528), the screen's message is that
**swirl number is the controlling parameter and 0.19 is on the wrong side of the useful range.**
There is no evidence here for a gentle-swirl optimum.

## Acceptance (CLAUDE.md §9)

| # | check | result |
|---|---|---|
| 1 | `checkMesh` | Mesh OK |
| 4 | **mass balance** | −3.20056e-03 / +3.20056e-03 → **−2.7e-10** ✓ |
| 5 | monitored quantities | stationary, RMS 6.6 % |
| 6 | mesh independence | ⚠ not established |
| — | **age identity** | **0.99788 (−0.212 %)** ✓ certified |
| — | y⁺ | area-avg **2.67**, max 8.97 — buffer layer ⚠ |

The `limitedLinear` age solve also certified on this case (−0.191 %) and gave 2.48 τ against
`upwind`'s 2.25 τ — a 9 % spread, matching the documented `upwind` smearing bias exactly. Read
2.25 τ as a lower bound and 2.48 τ as the better estimate; ε_a is then **20.2–22.3 %**, i.e.
the honest statement is *"barely distinguishable from the control"*.

## Files

- `anim_p1d_rad15_m0_x/animation.gif` — 60 frames, mid-width slice
- `anim_p1d_rad15_m0_x_log/`, `anim_p1d_rad15_m0_z_log/` — same views, **log scale 0.007–7 m/s**, for flow structure where the linear set saturates
- `anim_p1d_rad15_m0_z/animation.gif` — plan view; the swirl is visible here, not in the x-slice
- `vent_p1d_rad15_m0/` — 3D ventilation maps
- `mesh_rad15/` — mesh inspection renders
