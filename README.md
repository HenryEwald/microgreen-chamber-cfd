# Microgreen Growth Chamber CFD

3D internal-flow analysis of a microgreen growth chamber — a rectangular box with a curved
canopy, one fan inlet port and one outlet port — built on **OpenFOAM v2606** (ESI/openfoam.com).

> **Status: setup phase.** The directory scaffold, conventions, and solver roadmap are in
> place. Geometry, boundary-condition values, and operating conditions are still `TBD`
> placeholders. No case has been meshed or run yet, and no result in this repo should be
> treated as physical until the `TBD`s in [`CLAUDE.md` §6](CLAUDE.md) are filled from the
> chamber build spec.

## Objectives

| Phase | Question | Solver |
|---|---|---|
| 1 | Baseline isothermal airflow — does air reach the whole tray? | `simpleFoam` |
| 2 | Buoyancy-coupled flow — where does heat stratify under the LED load? | `buoyantSimpleFoam` |
| 3 | **Gravity parametric study** — how does the flow restructure as `g` varies (1 g → 0 g)? | `buoyantSimpleFoam` / `buoyantPimpleFoam` |
| 4 | Full chamber — plant canopy as a porous/resolved body with transpiration and CO₂ | `buoyantPimpleFoam` + `fvModels` |

Phase 3 is the point of the project. Results are reported against the Richardson number
`Ri = Gr/Re²` rather than raw `g`, since the interesting physics is the crossover between
fan-dominated (`Ri ≪ 1`) and buoyancy-dominated (`Ri ≫ 1`) regimes.

## Layout

```
├── CLAUDE.md      # full project spec: environment, physics, conventions, open questions
├── cad/           # STL geometry source (mm → m conversion notes)
├── templates/     # THE source of truth — cases are generated from here
│   ├── 0.orig/    #   initial + boundary conditions
│   ├── constant/  #   g, thermophysicalProperties, turbulenceProperties, fvModels
│   └── system/    #   blockMeshDict, snappyHexMeshDict, fvSchemes, fvSolution, controlDict
├── runs/          # generated cases — DISPOSABLE, git-ignored
├── scripts/       # case generation, sweep drivers, batch launchers
├── validation/    # analytical/experimental checks, mesh independence study
└── doc/           # notes, figures, chamber spec sheet
```

Cases in `runs/` are never hand-edited — they are produced from `templates/` by a script, so
any result is reproducible from a script plus a parameter set. Only `NOTES.md` files inside
`runs/` are tracked.

## Getting started

OpenFOAM is not sourced by `~/.bashrc`; every shell and script must activate it explicitly.

```bash
. /usr/lib/openfoam/openfoam2606/etc/bashrc
cd ~/OpenFOAM/henry-v2606/run/microgreenChamber
```

Meshing and solving, in order (always redirect to `log.<name>`):

```bash
blockMesh                            > log.blockMesh 2>&1
surfaceFeatureExtract                > log.surfaceFeatureExtract 2>&1
snappyHexMesh -overwrite             > log.snappyHexMesh 2>&1
checkMesh -allTopology -allGeometry  > log.checkMesh 2>&1
renumberMesh -overwrite              > log.renumberMesh 2>&1

decomposePar                         > log.decomposePar 2>&1
mpirun --cpu-set 0-7 --bind-to core -np 8 buoyantSimpleFoam -parallel > log.solve 2>&1
reconstructPar -latestTime           > log.reconstructPar 2>&1
```

The 8-rank / cores-0–7 default pins the solve to CCD0 of the Ryzen 9 7950X3D, whose 96 MB
V-cache is the best fit for a bandwidth-bound code at the 0.5–3 M cell target. There is no
GPU acceleration in this build — OpenFOAM here is 100 % CPU. See `CLAUDE.md` §3.

## The gravity sweep

The knob is a single file, `constant/g`, driven from `scripts/sweep_gravity.sh`:

```bash
foamDictionary -entry value -set "(0 0 -1.635)" constant/g
```

At exactly `g = 0` buoyancy vanishes and the flow is purely fan-driven, so `simpleFoam` is
both cheaper and better conditioned — it is used as the 0 g endpoint and cross-checked
against `buoyantSimpleFoam` with `value (0 0 0)`.

## Acceptance criteria

A run is not a result until all of these hold, and they are stated explicitly when reporting:

1. `checkMesh` passes, or every failure is listed and justified.
2. Residuals dropped ≥ 3–4 orders **and** flattened.
3. Global continuity error is small and not growing.
4. Mass balance closes: inlet flux + outlet flux ≈ 0 via `surfaceFieldValue`.
5. Monitored quantities are flat over the last N iterations — plotted, not eyeballed.
6. Mesh independence demonstrated for the quantity being reported.
7. The steady assumption is validated; a non-converged steady solution is never reported.

## Open questions

Chamber dimensions and canopy profile, fan spec and direction, the gravity regimes of
interest, LED power and placement, the objective function that defines "good", and whether
the chamber is sealed or leaky. All six block Phase 2 — see `CLAUDE.md` §10.

## Environment

OpenFOAM v2606 (api=2606, `linux64GccDPInt32Opt`) · gcc 13.3.0 · Open MPI 4.1.6 ·
ParaView 5.11.2 · gmsh 4.13.1 · Linux Mint 22.3 (Ubuntu 24.04 base).

This is **ESI/`.com` OpenFOAM**, not `.org` — `foamRun`/`foamMultiRun` and the `.org`
modular-solver structure do not exist here.
