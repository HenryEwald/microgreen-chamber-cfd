# Mesh independence — Phase 1, Q = 5 m³/h

Measured 2026-08-14. Satisfies the CLAUDE.md §9.6 requirement, with the caveats
in the last section — which are not small, read them before quoting any of this.

## The ladder

`m3` is **not buildable**: it extrapolates to ~33 M cells against the
`maxGlobalCells 20000000` cap, so snappy would stop refining *silently* and hand
back a mesh that is not level 3. The ladder therefore runs **downward** from m2.

`m1` is the coarsest mesh whose base cell divides the geometry exactly: the
internal dims are 360 / 560 / 430 thirds-of-a-mm and their GCD is 10, i.e.
10/3 mm = the m1 base. `m0` cannot be exact and takes 19 × 29 × 23, giving a
z cell of 6.522 mm against 6.667 mm in x and y — a 2.2 % anisotropy, aspect
ratio 1.02. Irrelevant: the background patch is entirely consumed by snappy and
the hood is a curved surface that never lay on a cell boundary at any level.

| | background | final cells | linear ratio `r` | steady 4000 iter |
|---|---|---|---|---|
| `m0` | 19 × 29 × 23 | **379,918** | — | **21.6 min** (4 ranks) |
| `m1` | 38 × 58 × 45 | **1,069,964** | 1.41 | **55.7 min** (8 ranks) |
| `m2` | 76 × 116 × 90 | **5,967,102** | 1.77 | ~5.2 h (projected) |

Both ratios clear the `r ≥ 1.3` that GCI wants. All three pass `checkMesh`
(non-orthogonality 59.5 / 63.6 / 65.0, skewness 3.43 / 3.41 / 3.16).

### ⚠ m0 needs level-3 tray refinement or it solves a different chamber

At the template's level 2 the local cell at m0 is 1.667 mm and the 2.5 mm tray
side slots get 1.5 cells across — **snappy seals them both.** It is a clean
`Mesh OK`, and the only symptom is the volume:

| | total volume | vs `V_air` = 2.5302e-3 m³ |
|---|---|---|
| m0, tray level 2 | 2.5147e-3 m³ | **−15.5 mL** |
| two tray slots | 1.56e-5 m³ | **15.6 mL** — 99 % of the deficit |
| m0, tray level 3 | 2.53008e-3 m³ | −0.12 mL ✓ |

Level 3 (0.833 mm, 3 cells across) restores the flow path, at 205 k → 380 k
cells. `scripts/generate_case.sh` now applies this automatically for `--mesh m0`.

**Always check total volume against `V_air`, not just `Mesh OK`.** A sealed slot
is invisible to every other mesh metric.

## Result — the metrics that decide the project's question

Averaged over iterations 1500–4000 (~2 oscillation periods; the flow is unsteady
at this `Q`, see CLAUDE.md §5.1). Fluctuation is 1σ over the same window at m1.

| metric | m0 (380 k) | m1 (1.07 M) | mesh diff | temporal fluctuation |
|---|---|---|---|---|
| **tray mean speed** [m/s] | 0.252112 | 0.251422 | **0.3 %** | **±3.6 %** |
| **tray CoV** (uniformity) | 0.457004 | 0.466248 | **2.0 %** | **±7.9 %** |
| tray slot flux [m³/s] | −3.878e-6 | −3.153e-6 | 23.0 % | ±12.3 % |
| slot split, % of `Q` | 0.279 % | 0.227 % | — | — |

**The headline finding: on the two tray metrics the project actually reports,
the discretisation error between 380 k and 1.07 M cells is 0.3 % and 2.0 %,
while the temporal fluctuation is ±3.6 % and ±7.9 %.** The mesh error is 4–12×
smaller than the unsteadiness it sits inside. Refining further does not buy a
better answer — it buys a more precise number for a quantity whose true value
oscillates by an order of magnitude more.

Consequence for run planning: **the transient should be run at m0.** Projected
from the measured 2.28 s/step anchor, a 6.6-τ transient costs 1.6 h at m0, 9.1 h
at m1 and 102 h at m2 — m2 pays twice, 5.6× the work per step *and* 2× the steps,
because the Courant-limited Δt halves with the cells.

`y+` supports this. Area-averages stay in the viscous sublayer at m0:

| patch | m0 avg | m1 avg | m0 max | m1 max |
|---|---|---|---|---|
| floor | 0.30 | 0.35 | 1.58 | 1.42 |
| walls | 0.74 | 0.77 | 11.92 | 6.06 |
| hood | **0.93** | **0.49** | 2.39 | 1.27 |
| tray | 1.21 | 1.18 | 5.09 | 4.92 |

## What this does NOT establish

1. **It is not a GCI.** These are SIMPLE-*iteration* averages of a run that never
   converged, because the flow is unsteady at `Q` = 5 m³/h (CLAUDE.md §5.1).
   SIMPLE iterations are not time. A rigorous independence study needs
   time-averages from the transient runs; this is a strong indicator, not a proof.
2. **It does not test slot resolution.** m0 and m1 both resolve the slots at
   0.833 mm — that was forced, to keep them open at all. The comparison varies
   everything *except* the slots.
3. **The slot flux is genuinely mesh-sensitive** (23 %). Anything that depends on
   the slots needs m1 or finer. It is 0.23–0.28 % of `Q` on both meshes, so it
   stays under the §7 threshold for dropping the refinement — but that threshold
   was about cost, not about trusting the number.
4. **Phase 2 is not covered.** The hood carries the LED load and its `y+` doubles
   at m0. Wall heat flux is far more mesh-sensitive than tray velocity — do not
   carry the m0 verdict into Phase 2 without re-checking it there.
5. `m2` has never been solved. Its row above is projected from the m1 rate.
