# First run — what happened

**Status: DONE, 2026-08-14.** The scaffold had never been executed (it was authored on the
Windows box, which has no OpenFOAM, no usable WSL distro and no Python — CLAUDE.md §2.1).
It has now been run on the Linux machine. **Eight defects, five of them blocking, were found
and fixed.** m1 and m2 both mesh, pass `checkMesh`, and solve.

Reproduce with:

```bash
. /usr/lib/openfoam/openfoam2606/etc/bashrc
cd ~/OpenFOAM/henry-v2606/run/microgreenChamber

scripts/generate_case.sh --name p1_smoke_m1 --mesh m1
cd runs/p1_smoke_m1 && ./Allrun
```

---

## What was wrong

Ordered by how badly it bit. "Silent" means it produced no error — the worst kind.

| # | Defect | Effect | Silent? |
|---|---|---|---|
| 1 | `. /usr/bin/openfoam2606` **execs** an interactive session | every script exited 0 having done nothing | ✅ silent |
| 2 | `chamber.stl` had **224 open edges** | snappy would have leaked into the background block | no — `--verify` caught it |
| 3 | `foamDictionary -set` expands `$nx/$ny/$nz` into `blocks` | `--mesh` did nothing; **every case was m2** | ✅ silent |
| 4 | `NCELLS` parsed from the `blocks` entry | picked up vertex labels → always 6 → always serial | ✅ silent |
| 5 | `areaNormalisedIntegrate` is not a v2606 operation | solver died on iteration 1 | no — FATAL IO ERROR |
| 6 | `checkMesh` gate grepped for any `***` | `-allGeometry` always reports concave cells → **no run would ever solve** | no |
| 7 | Second `decomposePar` reused `log.decomposePar` | `runApplication` skips it → parallel solve with no fields | ✅ silent |
| 8 | scripts not executable; `ACH` divided by 1000 | `sweep_*.sh` fail; ACH reported as 2 h⁻¹ not 1976 | partly |

Two more, non-blocking: `runApplication` does not propagate the solver's exit status (a crashed
solve printed the success checklist), and `runParallel` does no CPU pinning at all despite
CLAUDE.md §3.2 requiring `--bind-to core`.

### The one worth understanding: #1

`/usr/bin/openfoam2606` is two lines — `exec .../etc/openfoam "$@"`. **Sourcing** it replaces
the running shell with an interactive OpenFOAM session, which reads commands from the script's
stdin (`/dev/null` non-interactively) and exits. Everything below the source line is discarded
and the exit status is **0**. See the warning box in CLAUDE.md §2.

### The one that would have corrupted results: #3

`foamDictionary -set` rewrites the whole file through the parser, which **expands** dictionary
variables. The first `-set nx` call baked `blocks (hex (…) (76 116 90) …)` into the file; every
subsequent `nx/ny/nz` write was inert. `--mesh m1` and `--mesh m3` both produced m2. Since the
mesh-independence study (§9.6) is three runs that differ *only* by that flag, it would have
produced three identical meshes and "demonstrated" perfect independence. `generate_case.sh` now
uses anchored `sed` and verifies the result.

---

## What the mesh actually looks like

Measured, not estimated. Renders in [`doc/mesh/`](mesh/) — regenerate with
`pvpython scripts/render_mesh.py --case runs/<case>`.

| | m1 | m2 |
|---|---|---|
| Background block | 38 × 58 × 45 = 99 k | 76 × 116 × 90 = 793 k |
| **Final cells** | **1 069 964** | **5 967 102** |
| Mesh time | 141 s serial | 287 s on 8 ranks (CCD0) |
| Peak memory | — | 12 GB |
| `checkMesh` (standard) | **Mesh OK** | **Mesh OK** |
| Max non-orthogonality | 63.6 (avg 7.3) | **65.0** (avg 5.9) |
| Max skewness | 3.41 | 3.16 |
| Max aspect ratio | 13.8 | 11.9 |
| Number of regions | 1 (no leak) | 1 (no leak) |
| Layer coverage | 3.3–4.0 of 4 | 3.3–4.0 of 4 |

### Geometric fidelity — the strongest evidence the build is right

Every one of these is an independent check of a different part of the pipeline, and all of
them land on the analytic value:

| Quantity | Analytic | m1 mesh | m2 mesh |
|---|---|---|---|
| `V_air` (total volume) | 2.53018e-3 m³ | 2.53019e-3 | 2.53022e-3 |
| `hood` patch area | 0.0285250 m² | 0.0285248 | 0.0285250 |
| `floor` patch area (tray footprint excluded) | 0.0080250 m² | 0.0080250 | 0.0080250 |
| `tray` patch area (bottom face flush, so unwetted) | 0.0263750 m² | 0.0263750 | 0.0263750 |
| `inlet` / `outlet` area | 3.14159e-4 m² | 3.1111e-4 (−0.97 %) | 3.1319e-4 (**−0.31 %**) |

The floor and tray areas coming out exact confirms the tray really is flush on the floor with
its bottom face excluded from the wetted area. The port deficit is circle faceting and halves
with the cell size as it should; `flowRateInletVelocity` normalises by the *actual* patch area,
so the delivered mass flow is exact regardless — measured at iteration 78 of m1:

```
sum(inlet)  of phi = -0.00138889     target Q = 1.38889e-3 m3/s   exact
sum(outlet) of phi = +0.0013888707
                     ------------
                     -1.9e-8         CLAUDE.md 9.4 satisfied
```

### The `checkMesh` gate

`checkMesh -allTopology -allGeometry` reports `***Concave cells (using face planes)` on **both**
meshes — 22 089 cells (2.1 %) at m1, 76 320 (1.3 %) at m2. This is a property of layer cells and
refinement transitions on any snappy mesh, not a defect, and it is not one of the criteria
CLAUDE.md §7 names. `Allrun` now runs **two** passes: plain `checkMesh` as the acceptance gate
(both meshes report `Mesh OK`) and the `-allGeometry` pass as `log.checkMesh.extra` for the
report.

---

## Still open

1. **m3 is not buildable as configured.** Measured m1 → m2 growth is 5.6×, so m3 lands near
   **33 M cells** — over the `maxGlobalCells 20000000` cap, at which point snappy silently stops
   refining and hands back something that is *not* the level-3 mesh. See the warning in
   CLAUDE.md §7; the `traySlots` refinement box is the thing to shrink first.
2. **m2 non-orthogonality is 65.0** — exactly at the `maxNonOrtho` limit snappy was held to.
   The mesh is not failing, but there is no headroom, and `nNonOrthogonalCorrectors 1` in
   `fvSolution` is probably worth raising to 2 (CLAUDE.md §7 says to set it from what you
   actually got).
3. ~~**Phase 2 is untested.**~~ **CLOSED 2026-08-15 — and the prediction was right.**
   A deliberate 0.03-τ smoke test (`runs/p2_smoke_m0`) found exactly "more of the same class of
   dict error": `buoyantPimpleFoam` died on **time step 1** with
   `Entry 'rhoFinal' not found in dictionary "system/fvSolution/solvers"`. PIMPLE needs a
   `<field>Final` for every field it solves, and `rho` was a bare entry matching neither
   `p*Final` nor the `"(U|k|omega|e|h)Final"` regex. Phase 1 could never have caught it —
   `pimpleFoam` is incompressible and never solves `rho`. Fixed as `"rho.*"`.
   `externalWallHeatFluxTemperature mode power` on `hood` is confirmed correct, as is `p` being
   `calculated` (derived from `p_rgh`). See `validation/transient_matrix.md` §4b.
4. ~~**No converged solve yet.**~~ **SUPERSEDED 2026-08-15 — there will not be one.**
   The chamber does not reach a steady state at any flow rate tested: four steady runs across a
   16× range of shear-layer resolution, none within four orders of the `residualControl` target.
   The confined jet flaps. Phase 1 is `pimpleFoam` and every answer is a **time average plus a
   fluctuation level**. See CLAUDE.md §5.1 and `validation/transient_matrix.md`.

> **This document is a dated record of the 2026-08-14 first execution, not living
> documentation.** Items 1 and 2 above are still open; 3 and 4 are annotated rather than
> rewritten so the original predictions stay legible. For current state see `README.md` and
> `validation/`.

## Resolved from the original unverified list

| Item | Outcome |
|---|---|
| `make_geometry.py` | ran; was broken (#2); fixed and now self-verifies closure, orientation **and** enclosed volume |
| snappy patch naming | ✅ correct — `floor walls hood inlet outlet tray`, no prefixes |
| `background` patch has zero faces | ✅ fully consumed, `Number of regions: 1` |
| `sampledSurface` `bounds` syntax | ✅ accepted by v2606 |
| Cell counts | ❌ estimates were ~5× low — measured above |
| Layer settings | ✅ 3.3–4.0 of 4 layers, 66–97 % of target thickness |
| `areaNormalisedIntegrate` | ❌ does not exist — now `CoV` |
