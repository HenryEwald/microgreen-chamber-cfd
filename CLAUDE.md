# CLAUDE.md — Microgreen Growth Chamber CFD

Project instructions and reference for Claude Code. Read this before touching any case.

**Project:** 3D internal flow analysis of a microgreen growth chamber (rectangular box with a
curved canopy, one fan inlet port and one outlet port). Goals, in order:

1. Baseline isothermal airflow — velocity field, recirculation, dead zones, air exchange.
2. Buoyancy-coupled flow — temperature stratification with LED/canopy heat load.
3. **Gravity parametric study** — how the flow restructures as `g` varies (1 g → 0 g and beyond).
4. Full chamber model — plant canopy as a resolved/porous body with transpiration
   (humidity + latent heat) and CO₂ transport.

**Status:** Setup phase. Geometry, BC values, and operating conditions are `TBD` placeholders
(see [§6](#6-boundary-conditions--operating-parameters-placeholders)). Do not invent numbers to
fill them — leave `TBD` and ask, or run a documented sensitivity sweep instead.

---

## 1. Golden rules

1. **Never write into `/usr/lib/openfoam/openfoam2606`.** It is a root-owned Debian package
   install. It is read-only reference material (solver source, tutorials, templates) and gets
   replaced on upgrade. All project files live under
   `~/OpenFOAM/henry-v2606/run/microgreenChamber/`.
2. **Never `sudo` for anything OpenFOAM-related.** If a command needs root, it is the wrong
   command.
3. **Every case is disposable except `templates/`.** Cases in `runs/` are generated from
   `templates/` by a script, so any result can be reproduced from a script + a parameter set.
4. **`0.orig/` is the source of truth, never `0/`.** `0/` is a copy made by `Allrun`.
   `Allclean` deletes it.
5. **Placeholders are marked `TBD`.** Grep for `TBD` before declaring any result physical.
6. **No result without a `checkMesh` pass and a residual/continuity report.** See [§9](#9-verification--acceptance).

---

## 2. Environment

| Item | Value |
|---|---|
| OpenFOAM | v2606 (ESI/openfoam.com), api=2606 patch=0 |
| Install prefix | `/usr/lib/openfoam/openfoam2606` (root-owned, read-only) |
| Build | `linux64GccDPInt32Opt` — double precision, 32-bit labels, **optimised** |
| Activate | `source /usr/bin/openfoam2606` (or run `openfoam2606` for a subshell) |
| Compiler | gcc 13.3.0 |
| MPI | Open MPI 4.1.6 (`/usr/bin/mpirun`), `sys-openmpi` Pstream |
| Decomposition libs | `libscotchDecomp.so`, `libptscotchDecomp.so` (scotch + parallel scotch available) |
| ParaView | 5.11.2 (`paraview`, `pvpython`), `paraFoam` wrapper present |
| Meshing (external) | gmsh 4.13.1 at `~/gmsh-4.13.1-Linux64/bin/gmsh` |
| Python | 3.12.3, numpy 1.26.4, matplotlib 3.6.3. **No pyvista** — install into a venv if needed |
| OS | Linux Mint 22.3 (Zena), Ubuntu 24.04 base, kernel 6.17 |

**32-bit labels (`Int32`) cap a case at ~2.1 B cells** — irrelevant here, but it also means
label overflow is impossible at our target sizes. Nothing to work around.

`~/.bashrc` does **not** source OpenFOAM. Every shell and every script must activate it
explicitly. In non-interactive scripts use:

```bash
. /usr/bin/openfoam2606
```

---

## 3. Hardware profile and performance policy

| Component | Detail |
|---|---|
| CPU | AMD Ryzen 9 7950X3D — 16 cores / 32 threads, 1 NUMA node |
| **CCD0** | cores 0–7 (logical `0-7,16-23`) — **96 MB L3, 3D V-Cache die** |
| **CCD1** | cores 8–15 (logical `8-15,24-31`) — 32 MB L3, higher clocks |
| RAM | 61 GiB usable, 2 GiB swap |
| GPU | RTX 4080 SUPER, 16 GB, driver 595.71.05 |
| Disk | `/` on NVMe (`/dev/nvme0n1p5`), 116 GB free — **watch this, CFD output eats it** |
| Governor | `powersave` via `amd-pstate-epp` |

### 3.1 The GPU does not accelerate the solver

There is **no PETSc4FOAM, no AMGX, no CUDA linear solver** in this build (checked: no
`libpetscFoam`/`amgx` in `platforms/linux64GccDPInt32Opt/lib`). OpenFOAM here is **100 % CPU**.
The RTX 4080 SUPER is useful only for:

- ParaView rendering (large `foamToVTK` / OpenFOAM-reader datasets, volume rendering, ray tracing).
- Any future ML surrogate / plant-growth model work.

Do not propose GPU solver offload without first building PETSc + PETSc4FOAM against this
install — that is a separate project, and it is only worth it above ~20 M cells.

### 3.2 Core count and pinning — the important bit

OpenFOAM is **memory-bandwidth bound**, not FLOP bound. Consequences:

- **Never use SMT.** 32 MPI ranks on 16 cores is slower than 16. Use physical cores only
  (logical IDs 0–15).
- **Scaling saturates well before 16 cores.** Expect near-linear to ~8, diminishing to 16.
- **CCD0's 96 MB L3 is the headline feature for CFD.** If the per-rank working set fits in
  V-cache, CCD0-only runs can beat all-16-core runs. Cross-CCD communication also costs
  latency via Infinity Fabric.

**Default policy by mesh size:**

| Mesh size | `numberOfSubdomains` | Pinning | Rationale |
|---|---|---|---|
| < 0.5 M | 4 | CCD0 (`0-3`) | decomposition overhead dominates |
| 0.5–3 M | **8** | **CCD0 (`0-7`)** | **default — V-cache sweet spot** |
| 3–10 M | 8 or 16 | benchmark both | working set exceeds 96 MB; CCD1 may pay off |
| > 10 M | 16 | `0-15` | bandwidth-limited, use all cores |

**Keep ≥ 50 k cells/rank.** Below ~30 k, halo exchange dominates and scaling inverts.

Launch commands:

```bash
# CCD0-pinned, 8 ranks (default)
mpirun --cpu-set 0-7 --bind-to core -np 8 buoyantSimpleFoam -parallel > log.solve 2>&1

# All 16 physical cores
mpirun --cpu-set 0-15 --bind-to core -np 16 buoyantSimpleFoam -parallel > log.solve 2>&1
```

Always pass `--bind-to core`. Unpinned ranks get migrated across CCDs by the scheduler and
lose the L3 they warmed.

### 3.3 Other performance settings

- **Governor:** currently `powersave`. Before a long production run:
  `sudo cpupower frequency-set -g performance` (this is the one acceptable sudo, and it is a
  system setting, not an OpenFOAM action — ask the user, don't do it unprompted).
- **`renumberMesh -overwrite`** after meshing, before decomposition. Bandwidth-limited codes
  gain 10–25 % from the improved cache locality — this matters *more* than usual on the
  V-cache die.
- **`writeFormat binary;`** and `writeCompression off;` in `controlDict`. ASCII output is
  slow and huge. (The tutorials ship `ascii` — do not copy that.)
- **`purgeWrite 5;`** for transient runs unless you specifically need the full history. Disk
  is the binding constraint at 116 GB free.
- **`runTimeModifiable false;`** — avoids re-reading every dict every timestep.
- **Decomposition method:** `scotch` (no manual `n (x y z)` needed, handles the curved canopy
  and port geometry better than `hierarchical`). `hierarchical` only for regular block meshes.
- **`decomposePar -copyZero`** / **`redistributePar`** available if rebalancing is needed.
- Run parallel meshing too: `mpirun -np 8 snappyHexMesh -overwrite -parallel`.

---

## 4. File structure

### 4.1 Project tree (this repo)

```
~/OpenFOAM/henry-v2606/run/microgreenChamber/
├── CLAUDE.md              # this file
├── cad/                   # STL/geometry source, mm→m conversion notes
│   ├── chamber_walls.stl  # TBD  box + curved canopy, outward normals, ASCII or binary STL
│   ├── inlet_port.stl     # TBD
│   ├── outlet_port.stl    # TBD
│   └── tray.stl           # TBD  growing tray / substrate surface
├── templates/             # ← THE source of truth; cases are generated from here
│   ├── 0.orig/            # initial + boundary conditions (never edited in a run)
│   ├── constant/          # g, thermophysicalProperties, turbulenceProperties, fvModels
│   └── system/            # blockMeshDict, snappyHexMeshDict, fvSchemes, fvSolution,
│                          #   controlDict, decomposeParDict, functions/
├── runs/                  # generated cases — DISPOSABLE, git-ignored
│   └── <case-id>/         # naming: §8.1
├── scripts/               # case generation, sweep drivers, batch launchers
├── validation/            # analytical/experimental checks, mesh independence study
└── doc/                   # notes, figures, chamber spec sheet
```

### 4.2 Standard OpenFOAM case layout (what `runs/<case-id>/` contains)

```
runs/<case-id>/
├── 0.orig/{U,p,p_rgh,T,k,epsilon,nut,alphat,...}
├── 0/                     # copy of 0.orig made by Allrun; deleted by Allclean
├── constant/
│   ├── g                  # ← THE GRAVITY STUDY KNOB
│   ├── thermophysicalProperties
│   ├── turbulenceProperties
│   ├── fvModels           # porous canopy, transpiration sources (phase 4)
│   └── triSurface/        # STLs copied from ../../cad/
├── system/
│   ├── controlDict, fvSchemes, fvSolution
│   ├── blockMeshDict, snappyHexMeshDict, surfaceFeatureExtractDict
│   ├── decomposeParDict, topoSetDict
│   └── functions/         # #include'd function objects
├── Allrun, Allclean
└── log.*                  # one log per utility/solver invocation, always redirect
```

### 4.3 Read-only reference (`/usr/lib/openfoam/openfoam2606`)

| Path | Use |
|---|---|
| `applications/solvers/` | solver source — read to confirm what an option actually does |
| `tutorials/` | copy-from source for dict structure (see §5.3) |
| `etc/caseDicts/` | ready-made function-object snippets to `#include` |
| `etc/templates/` | skeleton cases |
| `src/` | model source: `finiteVolume/cfdTools/general/porosityModel/`, `fvOptions/sources/` |
| `platforms/linux64GccDPInt32Opt/bin/` | all executables |

---

## 5. Physics and solver roadmap

### 5.1 Phase plan

| Phase | Question | Solver | Fields |
|---|---|---|---|
| **1** | Does air reach the whole tray? | `simpleFoam` (steady, incompressible, isothermal) | `U p k epsilon nut` |
| **2** | Where does heat stratify? | `buoyantSimpleFoam` (steady, buoyant, compressible) | + `T p_rgh alphat` |
| **2b** | Is it actually steady? | `buoyantPimpleFoam` (transient) | same |
| **3** | **Gravity sweep** | `buoyantSimpleFoam` / `buoyantPimpleFoam` | vary `constant/g` |
| **4** | Full chamber w/ plants | `buoyantPimpleFoam` + `fvModels`, or `rhoReactingBuoyantFoam` | + humidity, CO₂ |

Start at Phase 1. Do not jump ahead — a buoyant case that will not converge is almost always
a mesh or BC problem that Phase 1 would have exposed in 5 minutes.

### 5.2 Key modelling decisions

**Buoyancy / compressibility.** `buoyantSimpleFoam` (full compressible, `rho`-based) is
preferred over `buoyantBoussinesqSimpleFoam` because the gravity sweep will push
Δρ/ρ around, and Boussinesq assumes it is small. Boussinesq is acceptable for Phase 2 quick
looks only. Buoyant solvers use `p_rgh` (= p − ρg·h) as the solved pressure — **`p` is
derived, do not set BCs on it independently of `p_rgh`.**

**Gravity study mechanics.** The knob is a single file, `constant/g`:

```
dimensions      [0 1 -2 0 0 0 0];
value           (0 0 -9.81);      // TBD orientation: confirm chamber -z is "down"
```

- Sweep plan: `g ∈ {0, 0.166 (Lunar), 0.379 (Mars), 1.0, ...} × 9.81 m/s²` — **TBD, confirm
  the target regimes** (spaceflight? centrifuge? hypergravity?).
- **At exactly `g = 0`**, buoyancy vanishes and the flow becomes purely fan-driven forced
  convection — `simpleFoam` is then the cheaper and better-conditioned choice. Use it as the
  0 g endpoint and cross-check it against `buoyantSimpleFoam` with `value (0 0 0)`.
- Report results against **Richardson number `Ri = Gr/Re²`**, not raw `g`. `Ri ≫ 1` =
  buoyancy-dominated, `Ri ≪ 1` = fan-dominated. The interesting physics is the crossover.
  This is the headline plot of the whole study.
- Expect *convergence behaviour to change across the sweep.* High-`Ri` cases are stiffer and
  may need transient (`buoyantPimpleFoam`) treatment even where the 1 g case ran steady.
  Don't force `simpleFoam`-style relaxation onto a case that has gone unsteady.

**Turbulence.** Fan-driven chamber flow at low velocity is **transitional, not fully
turbulent** — this is the single biggest modelling risk in the project.
- Default: `kOmegaSST` (better for low-Re near-wall and adverse pressure gradients than
  `kEpsilon`) with `nutkWallFunction`/`omegaWallFunction`.
- Check the cell Reynolds number at the ports. If `Re_port < ~2300`, consider `laminar` and
  say so explicitly in the run notes.
- `kEpsilon` only if matching a published chamber study that used it.

**Humidity.** Three escalating options — pick the cheapest that answers the question:
1. **Passive scalar** via the `scalarTransport` function object (`src/functionObjects/solvers/scalarTransport`).
   No feedback on density. Good for "where does moist air go".
2. **`energyTransport` function object** — adds a transported scalar with a source term.
3. **Real species** via `rhoReactingBuoyantFoam` with an air/H₂O mixture. Only when latent
   heat and vapour-density buoyancy actually matter (likely for Phase 4 + low-g).

There is a built-in **`comfort` function object** (PMV/PPD) that takes a `relHumidity` entry —
see `tutorials/heatTransfer/buoyantSimpleFoam/comfortHotRoom/system/FOcomfort`. Its PMV output
is for humans, not plants, but the humidity/saturation machinery is a useful reference.

**Plant canopy (Phase 4).** Two routes, both supported by this build:
- **Porous zone** — `explicitPorositySource` fvOption with `DarcyForchheimer` coefficients
  derived from leaf area density. Cheap, robust, the standard approach for vegetation.
  Available models: `DarcyForchheimer`, `powerLaw`, `fixedCoeff`
  (`src/finiteVolume/cfdTools/general/porosityModel/`).
- **Resolved geometry** — actual leaf STLs in `snappyHexMesh`. Expensive, only for a small
  representative patch.
- **Transpiration** — `semiImplicitSource` on the humidity field (vapour source) paired with
  a negative source on `h`/`T` (latent heat sink). `codedSource` if the flux needs to depend
  on local `U`, `T`, and vapour deficit.

### 5.3 Reference tutorials to copy from

| Need | Path (under `/usr/lib/openfoam/openfoam2606/tutorials/`) |
|---|---|
| Buoyant room + comfort + **age of air** | `heatTransfer/buoyantSimpleFoam/comfortHotRoom` |
| Buoyant cavity, clean BCs | `heatTransfer/buoyantSimpleFoam/buoyantCavity` |
| Heat source in an enclosure | `heatTransfer/buoyantSimpleFoam/hotRadiationRoom` |
| Component cooling in a box | `heatTransfer/buoyantSimpleFoam/circuitBoardCooling` |
| Enclosure ventilation | `incompressible/simpleFoam/windAroundBuildings` |
| STL → mesh workflow | `mesh/snappyHexMesh/` (esp. `block_with_curvature`, `gap_detection`) |
| Porous zones | `incompressible/simpleFoam/porousSimpleFoam` |
| Conjugate heat (walls) | `heatTransfer/chtMultiRegionFoam/` |

**Copy dicts, then strip them.** Tutorials carry `writeFormat ascii`, tiny `endTime`s, and
`hierarchical` decomposition — all wrong for us (§3.3).

---

## 6. Boundary conditions & operating parameters (PLACEHOLDERS)

> **Everything in this section is `TBD` until the physical chamber is specified.**
> Fill these in from the build spec / datasheets. Each row lists a *plausible* placeholder in
> brackets purely so cases can be dry-run — **these are not design values.**

### 6.1 Geometry

| Parameter | Symbol | Value | Notes |
|---|---|---|---|
| Chamber internal L × W × H | — | `TBD` [0.60 × 0.40 × 0.35 m] | box section |
| Canopy curvature | — | `TBD` | radius / profile of the curved top; arc or spline? |
| Tray area & height above floor | — | `TBD` | growing surface = key BC patch |
| Inlet port diameter/shape | `D_in` | `TBD` [Ø 80 mm] | round? rectangular? |
| Outlet port diameter/shape | `D_out` | `TBD` [Ø 80 mm] | |
| Port positions & orientation | — | `TBD` | **critical** — drives the whole flow topology |
| Coordinate convention | — | `TBD` | **confirm: is −z down?** `g` depends on it |
| Units in STL | — | `TBD` | CAD is usually mm; OpenFOAM is **m**. `scale 0.001` in snappy |

### 6.2 Flow / fan

| Parameter | Symbol | Value | Notes |
|---|---|---|---|
| Fan volumetric flow | `Q` | `TBD` [30 m³/h ≈ 0.00833 m³/s] | from fan datasheet at operating back-pressure |
| Inlet bulk velocity | `U_in` | `TBD` = `Q / A_in` | derive, don't guess |
| Air changes per hour | ACH | `TBD` = `Q / V_chamber` | target for microgreens: `TBD` |
| Fan curve (Δp vs Q) | — | `TBD` | needed if using a `fan`/`fanPressure` BC instead of fixed velocity |
| Inlet turbulence intensity | `I` | `TBD` [5 %] | fan outlets are turbulent; 5–10 % typical |
| Inlet turb. length scale | `l` | `TBD` [0.07 · D_in] | |
| Operating pressure | `p_op` | `TBD` [101325 Pa] | `pRef` in `fvSolution` |

**BC pattern (Phase 1–2), to be written into `0.orig/`:**

| Patch | `U` | `p_rgh` | `T` | `k`/`omega` |
|---|---|---|---|---|
| `inlet` | `flowRateInletVelocity` (preferred — takes `Q` directly, robust to area changes) | `fixedFluxPressure` | `fixedValue` `TBD` | `turbulentIntensityKineticEnergyInlet` / `turbulentMixingLengthFrequencyInlet` |
| `outlet` | `pressureInletOutletVelocity` or `inletOutlet` | `fixedValue` `$p_op` (or `totalPressure`) | `inletOutlet` | `inletOutlet` |
| `walls` | `noSlip` | `fixedFluxPressure` | `TBD` — see §6.3 | wall functions |
| `tray`/`canopy_surface` | `noSlip` | `fixedFluxPressure` | `TBD` — heat/moisture source patch | wall functions |

Prefer `flowRateInletVelocity` with `volumetricFlowRate` over a hand-computed `fixedValue` —
it stays correct when the port geometry changes, which it will.

### 6.3 Thermal

| Parameter | Value | Notes |
|---|---|---|
| Inlet air temperature | `TBD` [293.15 K / 20 °C] | ambient room air |
| Target chamber temperature | `TBD` [295–298 K / 22–25 °C] | microgreen setpoint |
| LED heat load | `TBD` [W total] | **dominant buoyancy source** — needs W and location |
| LED thermal model | `TBD` | resolved surface patch, `fvModel` volumetric source, or `fixedValue` T? |
| Wall thermal BC | `TBD` | adiabatic (`zeroGradient`) as first cut; `externalWallHeatFluxTemperature` if the enclosure loses heat |
| Wall material / thickness | `TBD` | only needed if going conjugate (`chtMultiRegionFoam`) |
| Substrate/tray temperature | `TBD` | evaporative cooling makes this < air temp |
| Radiation | `TBD` — assume **off** initially | LEDs radiate; `fvDOM`/`P1` if it proves to matter. See `hotRadiationRoomFvDOM` |

### 6.4 Humidity / species

| Parameter | Value | Notes |
|---|---|---|
| Inlet relative humidity | `TBD` [50 %] | |
| Target chamber RH | `TBD` [60–80 %] | microgreens like it high; mould risk above `TBD` |
| Transpiration rate | `TBD` [g H₂O · m⁻² · h⁻¹] | per tray area; the Phase-4 source term |
| Latent heat coupling | `TBD` | `h_fg` ≈ 2.45 MJ/kg at 20 °C |
| CO₂ inlet concentration | `TBD` [~420 ppm] | |
| CO₂ uptake rate | `TBD` | negative source over canopy, light-dependent |

### 6.5 Plant / canopy (Phase 4)

| Parameter | Value | Notes |
|---|---|---|
| Canopy height | `TBD` [20–50 mm] | microgreens are short — canopy may sit in the wall boundary layer |
| Leaf area density (LAD) | `TBD` [m²/m³] | → Darcy–Forchheimer coefficients |
| Darcy coeff `d` | `TBD` | viscous term |
| Forchheimer coeff `f` | `TBD` | inertial term; `f ≈ 2·C_d·LAD` is the usual canopy relation |
| Growth stage variation | `TBD` | day 3 vs day 10 canopies are very different — likely 2–3 discrete stages |

---

## 7. Meshing strategy

**Route:** `blockMesh` background block → `surfaceFeatureExtract` → `snappyHexMesh`.
gmsh is available as a fallback for the curved canopy if snappy struggles, via
`gmshToFoam` — but try snappy first; hex-dominant meshes converge better here.

- Background block: **isotropic cells**, aligned to the box axes. Target base cell `TBD`
  (start ~10 mm, refine down).
- Refinement: level 2–3 on the port walls and the curved canopy; surface layers on all
  no-slip walls (`nSurfaceLayers` 3–5) since the wall boundary layer *is* the physics for a
  short canopy.
- `snappyHexMesh` needs `insidePoint` inside the chamber void (internal flow — meshing the
  inside, not the outside).
- **Always** `checkMesh` after. Non-orthogonality < 65 and skewness < 4 before proceeding;
  set `nNonOrthogonalCorrectors` to match what you actually got.
- `renumberMesh -overwrite` before `decomposePar` (§3.3).
- Mesh independence study is mandatory before any published number — 3 levels, ~1.5–2×
  cell count each, tracked in `validation/`.

**Target sizes on this machine:** 1–3 M cells is comfortable and fast (minutes to ~an hour
steady). 5–10 M is a production run. RAM allows far more (~1 GB/M cells for steady
incompressible, more for buoyant/species) but wall-clock and the 116 GB disk bind first.

---

## 8. Workflow conventions

### 8.1 Run naming

`runs/<phase>_<variable>_<value>_<meshlevel>` — e.g.:

```
runs/p1_baseline_m2/          # phase 1, baseline, mesh level 2
runs/p3_g_0p166_m2/           # phase 3, g = 0.166 g0
runs/p3_g_0p000_m2/
runs/p4_lad_high_m3/
```

Use `p` for the decimal point. Every run gets a `NOTES.md` stating what changed, what the
question was, and the answer.

### 8.2 Logging

Every utility and solver call redirects to `log.<name>`. Never let output go to the terminal
only. `foamLog log.solve` extracts residuals; plot with matplotlib into `validation/`.
(Note: `foamMonitor` is **not** in this build — use `foamLog` + matplotlib.)

### 8.3 Sweeps

The gravity study is a parameter sweep over one file. Drive it from
`scripts/sweep_gravity.sh`: for each `g`, copy `templates/`, `foamDictionary`-set
`constant/g`, run, archive. Do not hand-edit N cases.

```bash
foamDictionary -entry value -set "(0 0 -1.635)" constant/g
```

### 8.4 Post-processing

- Function objects over post-hoc analysis wherever possible — cheaper and always in sync.
  Useful ones for this project: `age` (mean age of air = **ventilation effectiveness, the
  key chamber metric**), `fieldMinMax`, `volFieldValue`, `surfaceFieldValue` (flow balance
  at ports), `streamlines`, `wallShearStress`, `yPlus`, `comfort`.
- `#include "system/functions/..."` from `controlDict` rather than inlining.
- Check `etc/caseDicts/postProcessing/` for ready-made snippets before writing one.
- ParaView 5.11.2 for 3D; read the case directly with the OpenFOAM reader (`paraFoam`),
  only use `foamToVTK` when scripting with `pvpython`.

---

## 9. Verification & acceptance

A run is not a result until all of these hold. State them explicitly when reporting.

1. `checkMesh` passes (or every failure is listed and justified).
2. Residuals dropped ≥ 3–4 orders **and** flattened — not just "small".
3. **Global continuity error is small and not growing** (in the solver log).
4. **Mass balance closes:** inlet flux + outlet flux ≈ 0 via `surfaceFieldValue`. This
   catches bad BC pairings faster than anything else.
5. Monitored quantities (mean tray-level velocity, max T, age of air) are **flat over the
   last N iterations** — plot them, don't eyeball the last line.
6. Mesh independence demonstrated for the quantity being reported.
7. Steady assumption validated — if `simpleFoam`/`buoyantSimpleFoam` residuals plateau high
   or oscillate, the flow is unsteady and needs a transient run. Do not report a
   non-converged steady solution.

Report failures with the actual log output. Never describe a diverged or stalled run as done.

---

## 10. Open questions — resolve before Phase 2

1. **Chamber dimensions and canopy profile** — is there CAD, or does geometry need to be
   built from measurements? Determines whether `cad/` gets STLs or `blockMesh` gets an
   analytic canopy.
2. **Fan spec** — make/model, flow rate, and whether it is *pushing* into the inlet or
   *pulling* from the outlet. Changes which port gets the velocity BC.
3. **Gravity regimes of interest** — which values, and what is the physical context
   (spaceflight, lunar/Mars surface, centrifuge)? Drives whether `g = 0` exactly is needed.
4. **LED power and placement** — the dominant buoyancy source; without it Phase 2 is fiction.
5. **What decides "good"?** Uniformity of velocity over the tray? A minimum air speed at
   canopy level? ACH? Temperature spread? The objective function should be defined before
   optimising anything.
6. Is the chamber sealed or leaky? Affects whether inlet/outlet fluxes must balance exactly.

---

## 11. Quick command reference

```bash
. /usr/bin/openfoam2606                      # activate (required in every shell/script)
cd ~/OpenFOAM/henry-v2606/run/microgreenChamber

# mesh
blockMesh                        > log.blockMesh 2>&1
surfaceFeatureExtract            > log.surfaceFeatureExtract 2>&1
snappyHexMesh -overwrite         > log.snappyHexMesh 2>&1
checkMesh -allTopology -allGeometry > log.checkMesh 2>&1
renumberMesh -overwrite          > log.renumberMesh 2>&1

# parallel solve (CCD0, 8 ranks — default)
decomposePar                     > log.decomposePar 2>&1
mpirun --cpu-set 0-7 --bind-to core -np 8 buoyantSimpleFoam -parallel > log.solve 2>&1
reconstructPar -latestTime       > log.reconstructPar 2>&1

# parallel meshing (large meshes)
mpirun --cpu-set 0-7 --bind-to core -np 8 snappyHexMesh -overwrite -parallel > log.snappy 2>&1

# inspect / edit dicts without a text editor
foamDictionary constant/g
foamDictionary -entry value -set "(0 0 -3.72)" constant/g
foamDictionary system/fvSolution -entry relaxationFactors

# post
postProcess -func 'patchFlowRate(patch=inlet)' -latestTime
foamLog log.solve                 # → logs/ dir of residual series
paraFoam                          # or: touch case.foam && paraview case.foam
```

---

## 12. Notes for Claude

- **Ask before inventing physical parameters.** A wrong fan flow rate produces a
  beautiful, confident, meaningless result. `TBD` is the correct answer until told otherwise.
- Read the solver source under `applications/solvers/` when unsure what a keyword does —
  it is right there and authoritative. OpenFOAM documentation found online is often for
  the `.org` fork or an older API and will not match v2606.
- This is **`.com` OpenFOAM (ESI, v2606)**, not `.org` (v12). `foamRun`/`foamMultiRun` and
  the `.org` modular-solver structure **do not exist here** — the solvers are the classic
  named binaries listed in §5.1. Do not copy `.org` tutorial syntax.
- Prefer changing one thing per run. The gravity study is only interpretable if the mesh,
  turbulence model, and BCs are frozen across the sweep.
- When a case diverges, check in this order: mesh quality → BC consistency (esp. `p_rgh`
  vs `p` and inlet/outlet pairing) → relaxation factors → schemes. Not the reverse.
- Keep `templates/` clean and general. If a change only helps one run, it belongs in the run.
