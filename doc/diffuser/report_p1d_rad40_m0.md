# p1d_rad40_m0 — radial swirl, 12 vanes at 40° (`S` = 0.60) — **best of screen**

Twelve radial vanes on a Ø 12 mm hub, tilted 40°. The **vortex-breakdown-threshold** arm,
included in `design.md` §3a as the risky bracket, not the expected winner.

| | |
|---|---|
| solver / model | `pimpleFoam`, kOmegaSST, isothermal |
| mesh | m0 + level-4 on the vanes, **489,521** cells |
| `Q` | 11.52 m³/h |
| τ | 0.7279 s · endTime 4.82 s = 6.6 τ |
| Δt | 1.259e-4 s — `maxCo` bound |
| wall clock | **18.1 h** (8.2 h + 9.9 h across a deliberate pause/resume), 38,069 steps |
| frames | 60 |

## Result

| metric | value | vs control |
|---|---|---|
| tray mean \|U\| | **0.8970 ± 0.0350 m/s** (RMS **14.6 %**) | 0.3040 — **+195 %** |
| tray CoV | **0.528** — best in screen | 0.665 |
| ventilation ε_a | **40.6 %** — best in screen | 20.1 % — **doubled** |
| mean age | **1.23 τ** | 2.49 τ |
| hood age | 1.57 τ (**1.28× the mean**) ⚠ | 2.67 τ (1.07×) |
| worst cell | 2.99 τ | 5.29 τ |
| domain max \|U\| | 5.71 m/s = 2.24 × `U_in` | 3.41 |

**This is the only arm that improves both axes at once.** Ventilation effectiveness doubles, and
it is simultaneously the *most uniform* tray of the four — the only case that beats the plain
port on CoV. Mean air age falls from 2.49 τ to 1.23 τ, i.e. from "two and a half flow-throughs
stale" to "about one", which is the perfectly-mixed reference. Tray mean speed lands at 0.90 m/s
against a target band top of 0.8 — marginally over-driven, and the one metric that argues for
backing the tilt off slightly rather than pushing it further.

## The design.md prediction was wrong, in the useful direction

`design.md` §3a bracketed this case as the risk: *"`S` > 0.6 gives vortex breakdown = a standing
central recirculation = re-breathing"*, in a chamber 4.7 port diameters long against the 10–20
swirl needs to decay. **The re-breathing does not appear.** Worst cell 2.99 τ against the
control's 5.29 τ — the stagnant pockets got better, not worse.

Two observations that keep this from being settled:

1. **It is by far the most unsteady arm — tray RMS 14.6 %**, against 2.5 % (cascade), 3.7 %
   (control) and 6.6 % (rad15). A wandering breakdown bubble is exactly what that would look
   like. The mean is well resolved (`N_eff` = 14, SE 3.9 %), but a 14.6 % swing over the crop is
   itself a design fact, not just statistical scatter.
2. **Its hood is relatively the stalest in the screen** — 1.57 τ against a bulk of 1.23 τ, i.e.
   **28 % above its own mean**, where every other case sits 4–7 % above. rad40 mixes the working
   volume best and leaves the hood most distinct from it. Since the hood carries the LED in
   Phase 2, that is the region where this concept's advantage is least established.

## Acceptance (CLAUDE.md §9)

| # | check | result |
|---|---|---|
| 1 | `checkMesh` | Mesh OK; total volume 2.3245871e-3 m³ (diffuser displaces fluid) |
| 3 | continuity | cumulative 2.67e-7 against 3.2e-3 m³/s throughput = 8e-5 relative ✓ |
| 4 | **mass balance** | −3.20056000e-03 / +3.20056003e-03 → **3.0e-11** ✓ |
| 5 | monitored quantities | stationary; RMS 14.6 % is physical unsteadiness, not drift |
| 6 | mesh independence | ⚠ not established |
| — | **age identity** | **0.99784 (−0.216 %)** ✓ certified |
| — | y⁺ | area-avg **3.11**, max 10.58 — buffer layer ⚠ |

⚠ **The template's `limitedLinear` age scheme FAILED badly here** — identity error +2.3 % and a
reported **max age of 6101 τ**, a diverged solve. The numbers above are the `upwind` re-solve.
Because `upwind` smears (~9 % low on the mean), **ε_a = 40.6 % is an optimistic bound**; the
honest reading is "roughly double the control", not "40.6 % exactly".

## Run note — this case was paused and resumed

Stopped cleanly at t = 2.1689991 on a completed write (all 8 ranks verified), then resumed
bit-exactly from `startFrom latestTime`. Continuity carried across the join (1.1270e-7 →
1.1276e-7) and the reconstructed history is continuous over all 60 frames. `log.pimpleFoam.part1`
holds the pre-pause log.

## What the pictures show

`vent_p1d_rad40_m0/02_slice_x.png` shows a **broad fresh core** spreading from the diffuser
across the mid-height of the chamber — far wider than the control's pencil jet — with the stale
air confined to a **single pocket in the upper-left, the hood on the inlet side**.

This is the visual form of the numbers: the bulk is well mixed (1.23 τ), and what is left over
is one identifiable region rather than the control's two large stale slabs. It also confirms the
1.57 τ hood figure is not a diffuse effect but **a specific recirculation pocket above and
behind the inlet** — which matters, because a localised pocket is something a geometry change
can target, where a uniformly stale chamber is not.

The `_z` animation is where the swirl itself is visible; in the x-slice it reads only as
spreading.

## Files

- `anim_p1d_rad40_m0_x/animation.gif` — 60 frames, mid-width slice
- `anim_p1d_rad40_m0_x_log/`, `anim_p1d_rad40_m0_z_log/` — same views, **log scale 0.007–7 m/s**, for flow structure where the linear set saturates
- `anim_p1d_rad40_m0_z/animation.gif` — plan view; the swirl and its wander are clearest here
- `vent_p1d_rad40_m0/` — 3D ventilation maps
- `mesh_rad40/` — mesh inspection renders
