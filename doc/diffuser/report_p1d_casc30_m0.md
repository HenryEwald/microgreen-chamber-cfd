# p1d_casc30_m0 — cascade, 5 turning vanes at 30°

Five flat turning plates across the Ø 40 mm bore, tilted 30° to deflect the jet.

| | |
|---|---|
| solver / model | `pimpleFoam`, kOmegaSST, isothermal |
| mesh | m0 + level-4 `refinementSurfaces` on the vanes, **500,599** cells |
| `Q` | 11.52 m³/h (`KSYS` + 0.2 for the diffuser ⇒ ~2 % less flow than the control) |
| τ | 0.7279 s · endTime 4.82 s = 6.6 τ |
| Δt | 2.034e-4 s — bound by **`maxCo`**, not `maxDeltaT` |
| wall clock | **12.6 h**, 23,697 steps |
| frames | 60 |

## Result

| metric | value | vs target |
|---|---|---|
| tray mean \|U\| | **1.9985 ± 0.0076 m/s** (RMS 2.5 %) | **2.5× over the 0.8 m/s band top** |
| tray CoV | **0.812** | **worst of the four — worse than no diffuser** |
| ventilation ε_a | 38.8 % | nearly double the control |
| mean age | 1.29 τ | |
| hood age | 1.34 τ (1.04× the mean) | |
| worst cell | 2.53 τ | best worst-cell in the screen |
| domain max \|U\| | 6.90 m/s = **2.71 × `U_in`** | highest in the screen |

**This is the concept failing in exactly the way it was predicted to fail.** `design.md` §3a
flagged that a cascade "turns the jet without FILLING the cross-section (Ø 40 is 10 % of free
area)". The measurement confirms it: the vanes redirect the jet onto the tray rather than
spreading it, giving

- **excellent ventilation** — an impinging jet entrains hard, so ε_a nearly doubles and the
  worst cell is the best in the screen at 2.53 τ;
- **the worst uniformity in the screen** — CoV 0.812, i.e. it made the tray *less* uniform than
  the plain port did;
- a tray-level mean speed of **2.0 m/s**, which is not ventilation, it is scouring. Microgreens
  at 2 m/s over the substrate is a desiccation and mechanical-damage problem, and it also means
  the jet core is reaching the crop essentially undissipated (domain max 6.9 m/s at the vanes).

**Good ε_a is not sufficient.** This case is the reason the screen needs both axes: on mean age
alone it looks like a near-tie with the winner, and it is not a viable design.

## Acceptance (CLAUDE.md §9)

| # | check | result |
|---|---|---|
| 1 | `checkMesh` | Mesh OK |
| 4 | **mass balance** | −3.20056e-03 / +3.20056e-03 → **−1.0e-10** ✓ |
| 5 | monitored quantities | stationary, RMS 2.5 % — the *steadiest* arm |
| 6 | mesh independence | ⚠ not established |
| — | **age identity** | **0.99770 (−0.230 %)** ✓ certified — **but see below** |
| — | y⁺ | area-avg **3.16**, max **11.67** — buffer layer ⚠ |

⚠ **The template's `limitedLinear` age scheme FAILED on this case** — identity error +3.6 %,
with the linear solve diverging mid-corrector (final residual 8.0e7) and a reported max age of
21 τ. The numbers above are the `upwind` re-solve, which certifies. `upwind` is known to report
the mean ~9 % low, so ε_a = 38.8 % is an **optimistic bound**.

⚠ **y⁺ 3.16 average / 11.67 max on the vanes** is the buffer layer. Vane wall shear and the
near-vane loss are **not resolved**; the 0.2 added to `K_sys` for this diffuser is an assumed
figure, not a computed one.

## What the pictures show

`vent_p1d_casc30_m0/02_slice_x.png` shows the five vanes in section and, coming off them, a
**fresh plume angled sharply downward onto the tray**, which then sweeps along the tray surface
to the outlet. The whole chamber is markedly fresher than the control (uniform purple against
the control's orange) — this is a genuinely better-ventilated box.

But two things in the same image are the case against it:

1. **The fresh region hugs the tray**, which is why the tray-level speed is 2.0 m/s. The vanes
   converted an over-flying jet into an impinging one; they did not convert it into a plug.
2. **There is a distinct stale pocket in the bottom-left corner**, under and behind the
   deflected jet — the one region the redirected flow cannot reach, sitting at ~1.6–1.8 s while
   the bulk is near 1.0. It is on the **inlet** side, matching the Phase 1 finding that the dead
   air in this chamber pools beneath the incoming jet rather than in the hood.

## Files

- `anim_p1d_casc30_m0_x/animation.gif` — 60 frames. Watch the jet bend down onto the tray.
- `anim_p1d_casc30_m0_x_log/`, `anim_p1d_casc30_m0_z_log/` — same views, **log scale 0.007–7 m/s**, for flow structure where the linear set saturates
- `anim_p1d_casc30_m0_z/animation.gif` — plan view at the port centreline
- `vent_p1d_casc30_m0/` — 3D ventilation maps
- `mesh_casc30/` — mesh inspection renders
