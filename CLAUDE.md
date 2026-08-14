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
| Activate | **`. /usr/lib/openfoam/openfoam2606/etc/bashrc`** — see the warning below |
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
explicitly:

```bash
. /usr/lib/openfoam/openfoam2606/etc/bashrc
```

> ### ⚠ Do **not** `source /usr/bin/openfoam2606` in a script
>
> Verified 2026-08-14. `/usr/bin/openfoam2606` is two lines: `exec .../etc/openfoam "$@"`.
> Sourcing it **replaces the running shell with an interactive OpenFOAM session**, which then
> reads its commands from the script's stdin. In a non-interactive script that is `/dev/null`,
> so the session exits immediately — **the rest of the script never runs, and the exit status
> is 0.** It fails silently. `openfoam2606` typed at a prompt, to get a subshell, is fine; it
> is only sourcing that breaks.
>
> Two further traps when sourcing `etc/bashrc` from a `set -euo pipefail` script:
> - it reads `WM_PROJECT_SITE` unset → **`set -u` aborts it**;
> - its optional `_foamEtc -config adios2/hdf5/CGAL` probes return non-zero for packages this
>   build does not ship → **`set -e` aborts it part-way**, and bash then reports the cryptic
>   `pop_var_context: head of shell_variables not a function context`.
>
> So in a strict-mode script: `set +eu` → source → `set -eu`. `scripts/generate_case.sh` does
> exactly this.

### 2.1 There is a second machine — the Windows authoring box

This repo is also checked out on **Windows 11** at `C:\Users\Henry\Documents\microgreen-chamber-cfd`.
Verified 2026-08-13, that machine has:

| | |
|---|---|
| OpenFOAM | **none** |
| WSL | present, but only the `docker-desktop` utility distro — **no general-purpose Linux** |
| Docker | installed, **daemon stopped** |
| Python | **not installed** (Store alias stub only) |

**Consequence: nothing can be meshed, solved or `checkMesh`-ed on Windows.** That box is for
*authoring* — dicts, scripts, notes, and analysis of results copied back. All execution happens
on the Linux machine in §2. Do not write a workflow that assumes otherwise, and do not report
a mesh or a run as done from there.

Two things that *are* possible on Windows and worth using: writing the complete case (all
dicts are plain text) and numeric verification of derived geometry via PowerShell — the 1.06 mm
hood-offset error in §6.1 was caught that way.

If OpenFOAM is ever genuinely needed on Windows, the route is Docker
(`opencfd/openfoam-default:2606`, ~1.5 GB) with Docker Desktop started — **ask first**, it is a
large download and a different build from the documented Linux one.

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
├── cad/                   # reference only — NOT an input to the mesh
│   └── hood_sketch.png    # dimensioned sketch; the hood is analytic (parabola, §6.1)
│                          # STLs are GENERATED by scripts/make_geometry.py, never hand-made
├── templates/             # ← THE source of truth; cases are generated from here
│   ├── 0.orig/            # initial + boundary conditions (never edited in a run)
│   ├── constant/          # g, thermophysicalProperties, turbulenceProperties, fvModels
│   └── system/            # blockMeshDict, snappyHexMeshDict, fvSchemes, fvSolution,
│                          #   controlDict, decomposeParDict, functions/
├── runs/                  # generated cases — DISPOSABLE, git-ignored
│   └── <case-id>/         # naming: §8.1
├── scripts/               # case generation, sweep drivers, batch launchers
│   ├── make_geometry.py   # ← analytic geometry → constant/triSurface/*.stl
│   ├── generate_case.sh   # templates/ + parameters → runs/<case-id>/ + NOTES.md
│   ├── sweep_Q.sh         # Phase 1 flow ladder 5 / 2.5 / 1.25 m³/h
│   └── sweep_gravity.sh   # Phase 3, varies constant/g only
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
value           (0 0 -9.81);      // CONFIRMED: chamber -z is down, baseline = 1 g Earth
```

- **Baseline is 1 g Earth (`-9.81`), confirmed.** Phases 1–2 run at this value; it is the
  reference every sweep point is compared against.
- Sweep plan: `g ∈ {0, 0.166 (Lunar), 0.379 (Mars), 1.0, ...} × 9.81 m/s²` — **TBD, confirm
  the target regimes** (spaceflight? centrifuge? hypergravity?). Not blocking: Phases 1–2 are
  entirely defined at 1 g, so the sweep list can be settled later.
- Note the stratification is **stable** here (§6.3) — the sweep is measuring how much
  buoyancy *resists* fan-driven mixing, not how much it assists it.
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
- **`Re_port` depends on the operating flow, which is not yet known — so the model choice is
  not yet fixed.** `Re_port = 1319 · U_in`:

  | `Q` | `U_in` | `Re_port` | Regime | Model |
  |---|---|---|---|---|
  | 5 m³/h (free air, optimistic) | 4.42 m/s | 5 830 | turbulent | `kOmegaSST` |
  | 2.5 m³/h | 2.21 m/s | 2 915 | **transitional** | `kOmegaSST`, with caveats stated |
  | 1.25 m³/h | 1.10 m/s | 1 450 | laminar | `laminar` |

  Since 5 m³/h is a **free-air** rating (§6.2) the real operating point is likely in the
  transitional band — the worst case for modelling, where neither `laminar` nor a fully
  turbulent RANS closure is defensible. **Run the baseline both ways at the chosen `Q` and
  report the spread as a modelling uncertainty**, rather than picking one and calling it
  settled. This remains the single biggest modelling risk in the project.
- Even at the optimistic 5 m³/h, the jet decays fast in a 12 cm box: away from the core the
  local turbulent Reynolds number collapses and `kOmegaSST` is being used outside its comfort
  zone. Do not report near-wall heat flux as if it were resolved.
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

## 6. Boundary conditions & operating parameters

> **Geometry (§6.1) and flow (§6.2) are now specified** — supplied 2026-08-13, shown in
> **bold**, with derived quantities alongside. **Phase 1 is fully defined and can run.**
> **Thermal (§6.3) still needs the LED wattage**, which blocks Phase 2. Humidity (§6.4) and
> plant canopy (§6.5) remain `TBD` for Phase 4. Bracketed numbers are *plausible placeholders*
> — **not design values**. Grep for `TBD` before declaring any result physical.

### 6.1 Geometry

Partially specified as of 2026-08-13. **Bold = given by the user; `TBD` = still missing.**
Values quoted in cm as supplied, metres in brackets because dicts are in metres.

| Parameter | Symbol | Value | Notes |
|---|---|---|---|
| Chamber internal W × H × D | — | **12 × 9⅔ × 18⅔ cm** [0.12 × 0.0966667 × 0.1866667 m] | straight-walled box section; W is the face the ports sit on |
| Chamber external width | — | **12⅔ cm** [0.1266667 m] | ⇒ side walls ≈ **3.33 mm** each |
| Box volume | `V_box` | **≈ 2.165 L** [2.165e-3 m³] | 12 × 9.6667 × 18.6667 cm³ |
| Hood base (raised rectangle) | — | **0.5 cm** tall, full internal width | straight lip carrying the spline |
| Hood spline rise | — | **4.5 cm** above the rectangle ⇒ **5.0 cm** total above the box top | peak is on the centreline |
| Hood span | — | full **12⅔ cm external** (**12 cm internal**) width | |
| **Total internal height, floor → hood peak** | — | **14⅓ cm** [0.1433333 m] | 9⅔ box + 4⅔ hood. **Not 14⅔** — the 3.33 mm inward offset drops the internal apex. No flat ceiling; the box top is the spring line |
| Hood profile type | — | **PARABOLA** (analytic — see below). External: `y = 4.5·[1 − ((x − 6.3335)/6.3335)²]` above the lip line, `x` in cm from the outer wall | *not* a free spline. **No CAD export needed** |
| Hood internal surface | — | **normal offset inward 0.333 cm** — confirmed | ⇒ internal span **12.0 cm**, internal rise **4⅔ cm** above the spring line |
| Hood extrusion | — | **straight extrusion over the full 18⅔ cm depth** (barrel vault, flat end walls) — confirmed | |
| Hood construction | — | **hollow shell** — the chamber void continues up into the hood | one connected fluid region, not a separate cavity |
| Hood internal cross-section | — | **38.80 cm²** above the box top | numerically integrated from the true offset profile, 2026-08-13 |
| Hood internal arc length | — | **15.28 cm** | used for the LED fit check (§6.3) |
| Internal lip height | — | **0.394 cm** (external lip is 0.500) | the offset curve meets the side wall at z = 10.061 cm, *below* the external lip top — see the profile note |
| Wall / floor thickness | — | **0.333 cm** everywhere — confirmed | sides, floor and hood shell all 3.33 mm |
| Port shape & size | `D_in` = `D_out` | **round, r = 1 cm ⇒ Ø 20 mm**; `A_port` = **3.1416e-4 m²** | both ports identical |
| Port height | — | bottom edge **Z = 6 cm**, centre **Z = 7 cm** | consistent with r = 1 cm; leaves 1.67 cm of wall above the port if 9⅔ cm is the flat ceiling |
| Port Z datum | — | `TBD` — internal floor or external base of the chamber? | 3.33 mm-scale shift; matters at this size |
| Port face | — | **on a 12 cm-wide (W × H) face** | |
| Inlet/outlet arrangement | — | **one per opposite end face, mirror-symmetric** — through-flow along the 18⅔ cm depth | inferred from "the chamber is symmetric"; confirm |
| Port lateral position | — | **centred on the 12 cm width** (X = 6 cm) | ditto — implied by symmetry |
| Port construction | — | **simple circular cutouts, flush with the wall** — no stub, duct or flange | ⇒ the inlet BC sits on a flat disc; expect a top-hat profile, not a developed pipe profile |
| Port Z, internal datum | — | **bottom 5.667 cm, centre 6.667 cm, top 7.667 cm** above the internal floor | 6 cm external − 3.33 mm floor, **confirmed** |
| Tray | — | **11.5 × 2.5 × 12.5 cm** (W × H × D), modelled as a **box**, sitting **flush on the floor**, centred | top surface at **Z = 2.5 cm**, area **0.014375 m²** |
| Tray side slots | — | **2.5 mm each side × 2.5 cm tall × 12.5 cm long — OPEN, air passes through** | **confirmed as a real flow path** — must be resolved, see §7 |
| Tray end gaps | — | **3.08 cm each end**, open | ample; 18 cells at m2 |
| Total internal volume | — | **2.890 L** = 2.165 box + **0.724 hood** | verified numerically |
| Free air volume | `V_air` | **2.530 L** [2.530e-3 m³] — tray displaces 0.359 L | the ACH and residence-time denominator |
| Coordinate convention | — | X = 12 cm width, Y = 18⅔ cm depth, **Z vertical, −Z down** — **confirmed** by the 1 g assumption | `constant/g` = `(0 0 -9.81)` |
| Units in STL | — | `TBD` | CAD is usually mm; OpenFOAM is **m**. `scale 0.001` in snappy |

**Terminology — "canopy" is overloaded in this project.** Use **hood** for the curved chamber
lid (this section) and **plant canopy** for the vegetation (§6.5). Patch names: `hood`,
`walls`, `floor`, `tray`, `plantCanopy`, `inlet`, `outlet`.

### Hood profile — analytic, no CAD required

The profile is a **parabola**, given by the user 2026-08-13. In sketch coordinates (`x` cm
from the outer wall, `y` cm above the lip line at z = 0.5):

```
EXTERNAL:  y_ext = 4.5 · [ 1 − ( (x − 6.3335) / 6.3335 )² ]      x ∈ [0, 12.667]
```

**The mesh needs the INTERNAL surface** — the 0.333 cm normal offset inward. A true normal
offset of a parabola is **not** itself a parabola. **Do not substitute a fitted parabola for
it:** the closest internal parabola,

```
   y_int ≈ 4.1665 · [ 1 − ( (x − 6.3335) / 6.0 )² ]        ← REJECTED, see below
```

deviates by up to **1.06 mm**, worst **at the springing points** where the curve is steepest
(verified numerically 2026-08-13, not estimated). That is 0.6 cells at m2 and **1.3 cells at
m3** — i.e. it does *not* vanish under refinement, which would quietly corrupt the mesh
independence study. Cheap to avoid, so avoid it:

- **Generate the internal profile as the true normal offset, numerically, in the
  case-generation script.** For each `x` on the external parabola: `y = 4.5·[1−((x−6.3335)/6.3335)²]`,
  `dy/dx = −2·4.5·(x−6.3335)/6.3335²`, inward unit normal `n = (dy/dx, −1)/√(1+(dy/dx)²)`,
  offset point `p = (x, y) + 0.333·n`. Feed those points to a `blockMesh` `spline` edge.
  40 points is ample; any density is free; nothing is hand-transcribed and the geometry is
  byte-identical across every case in the gravity sweep.
- Apex is unaffected by the choice — the normal is vertical there, so `z_apex` = **14.333 cm**
  exactly. The disagreement is confined to the lower flanks.
- **The offset curve dips below the external lip top.** Numerically it meets the inner face of
  the side wall at **z = 10.061 cm**, i.e. the *internal* lip is **3.94 mm** tall, not 5 mm.
  The generator therefore builds the internal profile as: vertical wall at `x_int` = 0 from
  z = 9.667 → 10.061 cm, then the offset curve across to the mirror point. This is handled
  automatically by clipping the offset curve to `x_int ∈ [0, 12] cm`.
- **Residual ~1 mm uncertainty at that junction.** The real part probably has a fillet or a
  slightly different shell transition. Refine there, and record in `NOTES.md` that the bottom
  ~4 mm of the hood flank is ±1 mm uncertain. It is the only geometric approximation left.
- Note the end slope is `dy/dx` = 2 × 4.5 / 6.3335 = **1.42 (55° from horizontal)** — the hood
  meets the lip at a corner, not tangentially. `surfaceFeatureExtract` must capture that edge.
- Every internal dimension remains an exact multiple of ⅓ cm: 29/3 (box) + 14/3 (hood) = 43/3
  cm. The 10/3 mm mesh grid in §7 survives intact — 43 cells at m1.

**This chamber is small.** 12 cm across with a Ø 20 mm port: the port is 1/6 of the chamber
width, the whole domain is ~2–3 L, and the wall boundary layers are a significant fraction of
the volume. Consequences run through §6.2 (port velocity), §5.2 (`Re_port` — likely laminar)
and §7 (base cell must be ≈ 2 mm, not 10 mm).

**Vertical stack-up (Z, from the internal floor) — read this before interpreting any result:**

```
  0.00 cm  internal floor        (= 0.33 cm on the external datum)
  2.50 cm  tray top   ← growing surface, all metrics evaluated here
  4.50 cm  plant canopy top, young  (20 mm)
  5.67 cm  PORT bottom edge  ────────────
  6.67 cm  port centreline
  7.50 cm  plant canopy top, mature (50 mm)   ← INSIDE the port span
  7.67 cm  PORT top edge     ────────────
  9.67 cm  hood spring line (box top) — no flat ceiling, the hood starts here
 10.17 cm  top of the 0.5 cm lip, spline springs from here
 14.33 cm  hood peak, internal (centreline, x = 6 cm)   ← LED panel surface
```

Port heights are on the **internal** datum, derived from "Z = 6 cm from the external base"
minus an **assumed 3.33 mm floor thickness** — confirm that (§10.1 Q3); it shifts everything
here by up to 1/6 of a port diameter.

The port jet enters **3.2 cm above the tray** — but a mature 5 cm canopy reaches **7.5 cm**,
i.e. into the upper part of the port opening. The jet therefore fires *over* a young canopy
and *directly into* a mature one. Growth stage changes the flow topology, not just the
resistance (§6.5), and the Phase-1 empty-chamber baseline is only representative of day ~0.
Note also that **the entire hood volume (9.67 → 14.67 cm) sits above the jet** — 0.9 L, a
third of the chamber, with no direct forced-convection path into it and, per §6.3, a stable
thermal cap. Expect it to be the worst-ventilated region by a wide margin; the `age` function
object will show this immediately.

### 6.2 Flow / fan

| Parameter | Symbol | Value | Notes |
|---|---|---|---|
| Fan | — | **LD3007MS** — 30 × 30 × 7 mm DC axial | mounted over a Ø 20 mm port |
| Fan rating | `Q_free` | **5 m³/h — FREE AIR (zero back-pressure)** | **an upper bound, not the operating point** — see the note below |
| Operating flow | `Q_op` | **`TBD` — sweep 5 / 2.5 / 1.25 m³/h** | the single largest uncertainty in the project now |
| Inlet bulk velocity | `U_in` | `Q / A_port`, `A_port` = 3.1416e-4 m² ⇒ **4.42 / 2.21 / 1.10 m/s** | let `flowRateInletVelocity` compute it; do not hard-code |
| Chamber bulk velocity | `U_bulk` | `Q` / mid-plane free area (**126.05 cm²** = 116.0 box + 38.8 hood − 28.75 tray) ⇒ **0.110 / 0.055 / 0.028 m/s** | 40× slower than the jet — see the `Ri` note |
| Air changes per hour | ACH | `Q` ÷ 2.530 L ⇒ **1976 / 988 / 494 h⁻¹** | enormous, but normal for a 2.53 L box |
| Mean residence time | `τ` | **1.82 / 3.6 / 7.3 s** | the `age` function object should converge near this; much higher ⇒ dead zones |
| Port Reynolds number | `Re_port` | `= 1319 · U_in` ⇒ **5 830 / 2 915 / 1 450** | **turbulent / transitional / laminar.** The turbulence model is *not* settled — see §5.2 |
| Fan curve (Δp vs Q) | — | **`TBD` — needed** | LD3007MS datasheet; enables a `fan`/`fanPressure` BC and an actual operating-point prediction |
| Inlet turbulence intensity | `I` | `TBD` [5 %] | fan outlet, no stub to develop in; 5–10 % is the usual range |
| Inlet turb. length scale | `l` | `TBD` [0.07 · D_in = **1.4 mm**] | |
| Operating pressure | `p_op` | `TBD` [101325 Pa] | `pRef` in `fvSolution` |

> ### ⚠ 5 m³/h is free air — the chamber will not see it
>
> A 30 mm axial fan is a **high-flow, very low static-pressure** device; typical max static
> pressure for this class is ~20–50 Pa, and axial fans lose flow steeply against any
> back-pressure. This chamber presents a real load:
>
> | Loss | Estimate at `Q` = 5 m³/h |
> |---|---|
> | Port dynamic head, ½ρU² at 4.42 m/s | ≈ 11.7 Pa |
> | Inlet contraction into Ø 20 mm, K ≈ 0.5 | ≈ 5.9 Pa |
> | Outlet discharge, K ≈ 1.0 | ≈ 11.7 Pa |
> | Internal + canopy | further, unquantified |
> | **Total** | **≳ 30 Pa — at or beyond the fan's likely shut-off** |
>
> There is also a **geometric mismatch**: a 30 mm fan blowing into a 20 mm hole is only 44 %
> of the fan's face area. **Expect the delivered flow to be well below 5 m³/h — plausibly
> half or less.** Treating 5 m³/h as the design point would overstate every mixing metric in
> the study.
>
> **Do this instead:**
> 1. Get the **Δp–Q curve** from the LD3007MS datasheet. With it, the operating point is a
>    proper fan-curve/system-curve intersection, and a `fan`/`fanPressure` BC finds it
>    self-consistently rather than being asserted.
> 2. Failing that, **run the ladder 5 / 2.5 / 1.25 m³/h** and report every metric as a
>    function of `Q`. This is not optional padding — the answer changes qualitatively across
>    that range (see `Re_port` above).
> 3. Best of all, **measure it**: an anemometer at the outlet, or a soap-film/bag timing test,
>    beats any datasheet number for a system this restricted.

> ### Two velocity scales — define the `Ri` reference before Phase 3
>
> `U_in` = 4.42 m/s and `U_bulk` = 0.110 m/s differ by 40×, and `Ri ∝ 1/U²`, so the choice of
> reference velocity moves the Richardson number by **~1600×**. At the current working load
> (38.4 W ⇒ ΔT = 22.9 K, `L` = 0.0967 m): `Ri(U_in)` ≈ **0.004** (fan-dominated) vs
> `Ri(U_bulk)` ≈ **6.0** (strongly buoyancy-dominated). Same chamber, same instant.
>
> Both are "true": the jet core is forced-convection, the bulk of the chamber — and especially
> the hood volume above the jet — is buoyancy-controlled. **This chamber is not one regime.**
> So: pick **one** documented reference scale for the headline `Ri` sweep plot (`U_bulk` is the
> more honest choice — it describes the region the gravity sweep actually changes), state it
> on the axis label, and report the local `Ri` field as well. Do not let the crossover point
> be an artefact of an undeclared normalisation.

> ### ⚠ Geometric symmetry does **not** make inlet/outlet interchangeable
>
> The chamber is mirror-symmetric about the mid-depth plane, so it is tempting to say the two
> ports are equivalent. **The flow is not symmetric under the swap.** An inlet is a momentum
> source — a directed jet that penetrates several diameters and organises the whole
> recirculation. An outlet is a sink — potential-flow-like, drawing near-isotropically from a
> region ~1 diameter across, with essentially no directional reach. This asymmetry is one of
> the standard results in room-ventilation flow, and it is *stronger* in a small box like this
> where the jet crosses a good fraction of the domain.
>
> Practical consequences:
> - Whichever port is the **inlet** determines which end of the tray gets swept and which end
>   is the dead zone. Swapping them mirrors the *geometry* but gives a genuinely different
>   velocity field over the tray, not a mirror image of the first.
> - Adding buoyancy (Phase 2) breaks the symmetry further: gravity picks out a direction the
>   geometry does not, and the hood + LED heat load sit above the jet.
> - **So: the choice is not irrelevant, and it is worth a run each.** Cheap insurance — the
>   two cases share a mesh and differ only in which patch carries `flowRateInletVelocity`.
>   Treat "push through port A" vs "pull through port A" as a Phase-1 sub-study and report
>   tray-level uniformity for both. If the fan can only be mounted one way, say which.

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
| LED panel | **WS2812B 16 × 16 addressable RGB, 256 px** | 10 mm pitch ⇒ **160 × 160 mm**, area **0.0256 m²** |
| LED location | **curved over the hood interior, centred, covering most of it** | the heat source is the *ceiling*, directly above the tray |
| LED fit | 160 mm across an internal hood arc of **161.6 mm** (151.6 curved + 2 × 5 lip); 160 mm along the 186.7 mm depth, 13 mm clear each end | **covers essentially the whole hood arc** — independently consistent with "covers most of it" ✓ |
| LED thickness | **negligible** — zero-thickness skin on the hood surface | no flow blockage, no separate solid region |
| LED full-white max | 256 px × 60 mA × 5 V = **76.8 W** | 20 mA per R/G/B channel, the WS2812B spec |
| **LED power (working value)** | **38.4 W — 50 % of full white.** ⚠ **PLACEHOLDER, see note** | `TBD` pending the real duty; **this value overheats the chamber** — energy balance below |
| LED heat flux | **1500 W/m²** = 38.4 W / 0.0256 m² | the `q` to set on the hood patch |
| LED thermal model | **heat flux on the hood patch** — `externalWallHeatFluxTemperature`, `mode power` | put `P` in the dict, not `q`, so the area is never double-counted |
| Optical→thermal fraction | **assume 1.0** | the chamber is closed and the walls/plants absorb essentially all emitted light; for a sealed box, **electrical power in = heat load**. Photosynthesis consumes < 1 %, ignore it |
| Wall thermal BC | `TBD` | adiabatic (`zeroGradient`) as first cut; `externalWallHeatFluxTemperature` if the enclosure loses heat |
| Wall material / thickness | `TBD` | only needed if going conjugate (`chtMultiRegionFoam`) |
| Substrate/tray temperature | `TBD` | evaporative cooling makes this < air temp |
| Radiation | `TBD` — assume **off** initially | LEDs radiate; `fvDOM`/`P1` if it proves to matter. See `hotRadiationRoomFvDOM` |

> ### ⚠ Zero-CFD energy balance — the LED power is thermally constrained to ~5 W
>
> Steady state, adiabatic walls, all LED power to air. The ventilation stream is the only heat
> sink, so `P = ṁ · c_p · ΔT`. At `Q` = 5 m³/h: `ṁ` = 1.667e-3 kg/s, `ṁ·c_p` = **1.675 W/K**.
>
> **`ΔT = 0.60 · P`** — every watt raises the chamber ~0.6 K above inlet.
>
> | LED duty | `P` | `ΔT` | Chamber T (20 °C inlet) | Verdict |
> |---|---|---|---|---|
> | 100 % white | 76.8 W | **45.8 K** | 66 °C | cooks the crop |
> | 50 % | 38 W | 22.7 K | 43 °C | far too hot |
> | 25 % | 19 W | 11.3 K | 31 °C | too hot |
> | ~13 % | 10 W | 6.0 K | 26 °C | marginal |
> | **~7 %** | **5 W** | **3.0 K** | **23 °C** | **in the 22–25 °C target band** |
>
> **So the panel cannot run above roughly 8 W without the chamber overheating**, no matter how
> good the mixing is — and at the *reduced* flow the free-air caveat implies (§6.2), the
> ceiling is lower still: at 2.5 m³/h, `ΔT = 1.19·P` and 5 W already gives 26 °C.
>
> This is a **design constraint, not a CFD result**, and it reframes the study: CFD decides
> *uniformity* — whether the heat is spread evenly or pooled in the hood — while the *mean*
> temperature is already fixed by this balance. If the intended duty is much above ~7 %, the
> real conclusion is that the chamber needs more airflow or wall cooling, and no amount of
> flow-field optimisation fixes it.
>
> Caveats, both of which raise the allowable power: real walls are not adiabatic (thin plastic
> at 3.33 mm loses heat to the room), and transpiration is an evaporative sink (Phase 4).
> Neither changes the order of magnitude.
>
> #### ⚠ NOTE — COME BACK TO THIS: the 50 % working value is thermally non-viable
>
> The current placeholder is **38.4 W (50 % white)**, chosen 2026-08-13 to let Phase 2 proceed.
> Per the table above that is **ΔT ≈ 22.9 K ⇒ 43 °C at 5 m³/h**, and ~66 °C at the more likely
> 2.5 m³/h. Microgreens want 22–25 °C. **Runs at this power characterise the flow and
> stratification structure; their absolute temperatures are not a prediction of the built
> chamber.** Say so explicitly in every `NOTES.md` and on every figure axis.
>
> Two further consequences of running 38.4 W:
> - `Ri` ≈ 6–7 on the `U_bulk` scale ⇒ **strongly buoyancy-dominated and stably stratified.**
>   Expect `buoyantSimpleFoam` to be stiff or to refuse to converge; budget for
>   `buoyantPimpleFoam` (§9.7) rather than forcing relaxation onto it.
> - Local hood temperatures will run well above the 43 °C *mean*, because the hood is the
>   worst-ventilated volume (§6.1) and the heat source is on its surface. Report max hood `T`
>   separately from bulk `T` — it is the number that would damage the panel.
>
> **Resolve by:** measuring or specifying the actual intended duty. If the answer really is
> 50 %, the finding is that the chamber design needs rework, not that the CFD needs refining.

> ### The LED is on the ceiling — this chamber is **stably stratified**
>
> Heat enters at the **top** (hood-mounted LED) and the coolest surface is at the **bottom**
> (tray, likely evaporatively cooled below air temperature). That is heating-from-above:
> warm light air sits on cold dense air, which is the **stable** configuration. Buoyancy here
> **suppresses** vertical mixing rather than driving it — the opposite of the usual
> heated-floor room case that most of the reference tutorials model.
>
> This reframes the whole project:
> - **The fan is the only thing mixing the chamber.** There is no helpful convective cell to
>   fall back on. If the jet does not reach a region, nothing else will.
> - Expect a **warm cap under the hood** and a stagnant cool layer over the tray, with the
>   jet's momentum the only mechanism breaking through it. Dead zones will be worse, not
>   better, than the isothermal Phase-1 baseline suggests.
> - **The gravity sweep result may run backwards from intuition.** Higher `g` ⇒ stronger
>   stable stratification ⇒ *more* resistance to vertical mixing ⇒ *worse* tray-level air
>   exchange. At `g = 0` stratification vanishes entirely and the chamber becomes pure
>   forced convection, which may well be the **best-mixed** case in the sweep.
>   Do not assume "less gravity = worse" — for this configuration the opposite is plausible,
>   and demonstrating it is arguably the headline result (§5.2, `Ri` crossover).
> - Consequence for Phase 2: if the stratification is strong, `buoyantSimpleFoam` steady may
>   stall or go unsteady. Budget for `buoyantPimpleFoam` (§9.7).

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
| Canopy height | `TBD` [20–50 mm] | microgreens are short — canopy may sit in the wall boundary layer. **Note the chamber is only 96.7 mm internally: a 50 mm canopy fills half of it, and the port bottom edge is at 60 mm — i.e. barely above a mature canopy.** Growth stage may change the flow topology, not just the resistance |
| Leaf area density (LAD) | `TBD` [m²/m³] | → Darcy–Forchheimer coefficients |
| Darcy coeff `d` | `TBD` | viscous term |
| Forchheimer coeff `f` | `TBD` | inertial term; `f ≈ 2·C_d·LAD` is the usual canopy relation |
| Growth stage variation | `TBD` | day 3 vs day 10 canopies are very different — likely 2–3 discrete stages |

---

## 7. Meshing strategy

**Route:** `blockMesh` background block → `surfaceFeatureExtract` → `snappyHexMesh`.
gmsh is available as a fallback for the curved hood if snappy struggles, via
`gmshToFoam` — but try snappy first; hex-dominant meshes converge better here.

**No CAD is required — the STLs are generated.** `scripts/make_geometry.py` writes
`constant/triSurface/{chamber,tray}.stl` directly from the §6.1 parameters: the hood as the
numerically computed normal offset of the parabola, the ports as circular openings in the end
walls, the tray as a box. snappy still wants a triangulated surface — that is unavoidable —
but nothing is hand-modelled, there is no `scale 0.001` unit trap, and the geometry is
byte-identical across every case in the gravity sweep.

Run it with `--verify`: it checks every edge is shared by exactly two facets and refuses to
hand snappy a leaky surface. `Allrun` passes `--verify` automatically. It also prints the
derived hood apex / lip height / cross-section / `V_air` against their expected values, so a
parameter change that breaks the geometry is caught at generation time rather than in
`checkMesh`.

**y⁺ warning.** At `U_in` = 4.42 m/s the near-wall cells at m2 will land in the buffer layer
(`y⁺` ≈ 1–30) — the worst place to be for wall functions. v2606's `nutkWallFunction` /
`omegaWallFunction` use continuous blending so this is *handled*, not *ideal*. Run the `yPlus`
function object every case and report the distribution, not just the max. If large areas sit
at `y⁺` ≈ 5–15, say so rather than quietly reporting wall heat flux as if it were resolved.

- Background block: **isotropic cells**, aligned to the box axes. **Base cell = 10/3 mm and
  its halves** — every internal dimension (120, 96⅔, 186⅔ mm, and 146⅔ mm if the hood sits on
  top) is an exact multiple of 10/3 mm, so `blockMesh` divides cleanly with no stray sliver
  cells at the far walls.

  Full internal height is **14⅓ cm = 43 base cells at m1** — exact, since 29/3 + 14/3 = 43/3 cm.

  | Level | Base cell | Background (incl. 1-cell margin) | Final cells | Run as |
  |---|---|---|---|---|
  | `m1` | 3.333 mm | 38 × 58 × 45 = 99 k | **1.07 M** (measured) | **serial**, ~2 min |
  | `m2` | 1.667 mm | 76 × 116 × 90 = 793 k | **5.97 M** (measured) | 8 ranks CCD0, ~5 min |
  | `m3` | 0.833 mm | 152 × 232 × 180 = 6.35 M | **~33 M** (extrapolated) | ⚠ see below |

> ### ⚠ Measured 2026-08-14 — the earlier estimates in this table were ~5× low
>
> The original entries (0.15–0.25 M / 1.2–1.6 M / 8–10 M) counted the hood carve but not the
> **refinement regions**, which dominate. Actual m1 → m2 growth is **5.6×**, not 8×, because
> surface-driven refinement scales with area rather than volume.
>
> Consequences, in order of severity:
>
> 1. **`m3` is not buildable as configured.** ~33 M cells exceeds the `maxGlobalCells 20000000`
>    cap in `snappyHexMeshDict`, so snappy would *silently stop refining* and produce a mesh
>    that is not the level-3 mesh you asked for — the worst possible failure mode for a mesh
>    independence study (§9.6). It is also ~35 GB+ of RAM.
> 2. **`m1` is no longer a smoke test** at 1.07 M cells and ~2 minutes, though it is still
>    fast enough to be useful as one.
> 3. `m2` at 5.97 M sits in the §3.2 "3–10 M, benchmark 8 vs 16 ranks" band, not the
>    "0.5–3 M, 8 ranks" band it was assumed to be in.
>
> **The refinement regions are where the cells are going, and `traySlots` is the worst
> offender:** it is a single box spanning the *entire* tray footprint (12 × 13.1 × 2.8 cm) at
> level 2, when the thing it exists to resolve is two 2.5 mm slots at the extreme edges in `x`.
> Almost all of that volume is either inside the tray solid or open chamber that does not need
> level 2. Replacing it with two thin boxes hugging the slots (`x` ∈ [−1, 4] mm and
> [116, 121] mm) would cut the count substantially at identical slot resolution, and is the
> obvious first move before attempting m3. **Not done — it changes the refinement the study is
> built on, so it is the user's call.**
- Ø 20 mm port ⇒ **12 cells across the port at m2**, 24 at m3, before refinement. Level 2 on
  the port walls gives 48 at m2 — enough to resolve the jet that sets the whole flow field.
- **The tray side slots are the tightest feature in the mesh, and they are open.** The tray is
  flush with the floor only, so each 2.5 mm × 2.5 cm × 12.5 cm side slot is a real flow path.
  At base resolution that is 1.5 cells (m2) / 3 cells (m3) across — **not resolvable**.
  Mandatory: **local refinement level 2 on the tray surfaces** ⇒ 0.42 mm cells ⇒ **6 cells
  across the slot** at m2, 12 at m3, plus snappy `gap_detection` (see
  `tutorials/mesh/snappyHexMesh/gap_detection`). Layer insertion inside a 6-cell slot will
  fight you — expect to set `nSurfaceLayers 0` on the tray sides, or accept fewer layers
  there, and check `checkMesh` skewness in that region specifically.
- **Sanity-check the slots before trusting them.** Two slots of 2.5 × 25 mm = 125 mm² total,
  vs the 314 mm² port. They are not negligible on area, but they are a high-aspect-ratio,
  high-resistance path — how much air actually goes through is a result, not an assumption.
  Put a `surfaceFieldValue` on a slot cross-section and report the split. If it turns out to
  be < 1 % of `Q`, the refinement can be dropped at m3 and the study gets cheaper.
- The tray is an axis-aligned box ⇒ `blockMesh` blocks or a `searchableBox`; the ports are
  cylinders ⇒ `searchableCylinder`; the hood is a `spline` edge. **No STL anywhere in this
  case**, so `cad/` stays empty and there is no mm→m scaling trap.
- Refinement: level 2–3 on the port walls and the curved hood; surface layers on all
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

### 10.1 Geometry — **COMPLETE.** Nothing outstanding.

Fully analytic, fully parametric, no CAD or STL. The internal hood profile is the *numerically
computed* normal offset (§6.1) — a fitted parabola was tried and rejected at 1.06 mm error.
The only geometric approximation left is ±1 mm at the hood/lip junction, over the bottom ~5 mm
of the flank.

### 10.2 Deferred — flagged, working values in place, **come back before publishing**

| # | Open item | Working value | Where |
|---|---|---|---|
| 1 | **LD3007MS Δp–Q curve** — 5 m³/h is free air, delivered flow is likely well below it | sweep **5 / 2.5 / 1.25 m³/h**, report everything vs `Q` | §6.2 |
| 2 | **LED duty / brightness** | **38.4 W (50 % white)** — thermally non-viable, see the warning | §6.3 |

Both are **noted, not resolved.** Item 1 changes the turbulence regime (§5.2) and every mixing
metric; item 2 makes the absolute temperatures unphysical while leaving the flow structure
informative. Neither blocks Phase 1. Every run's `NOTES.md` must state which working value it
used, and no figure derived from them goes out without the caveat on it.

### 10.3 Resolved

| Question | Answer | Date |
|---|---|---|
| Chamber internal dimensions | 12 × 9⅔ × 18⅔ cm | 2026-08-13 |
| Port size and height | Ø 20 mm, bottom edge Z = 6 cm | 2026-08-13 |
| Hood rise | 0.5 cm lip + 4.5 cm spline = 5.0 cm | 2026-08-13 |
| Port construction | plain circular cutouts, no stubs | 2026-08-13 |
| Port arrangement | one per opposite end face, centred, mirror-symmetric *(inferred)* | 2026-08-13 |
| Tray | 11.5 × 2.5 × 12.5 cm box, centred on the floor | 2026-08-13 |
| LED location | curved over the hood interior ⇒ **stable stratification**, see §6.3 | 2026-08-13 |
| Baseline gravity | 1 g Earth, `(0 0 -9.81)`, −Z down | 2026-08-13 |
| Total internal height | **14⅔ cm** floor → hood peak; **no flat ceiling** | 2026-08-13 |
| Hood profile | **parabola**, `y = 4.5·[1 − ((x−6.3335)/6.3335)²]` external; analytic internal offset | 2026-08-13 |
| Tray side slots | **open** — tray is flush with the floor only ⇒ must be meshed | 2026-08-13 |
| Port Z datum | measured from the **external base** | 2026-08-13 |
| Fan | **LD3007MS**, 5 m³/h **free air** — an upper bound, not the operating point | 2026-08-13 |
| Hood internal surface | 3.33 mm normal offset ⇒ internal height **14⅓ cm**, span 12.0 cm | 2026-08-13 |
| Wall/floor thickness | **3.33 mm** throughout | 2026-08-13 |
| Hood extrusion | straight barrel vault, hollow shell, flat end walls | 2026-08-13 |
| LED panel | **WS2812B 16×16**, 160 × 160 mm, 0.0256 m², max 76.8 W; negligible thickness | 2026-08-13 |
| CAD/STL needed? | **No** — fully parametric `blockMesh` + `snappyHexMesh` | 2026-08-13 |
| Turbulence model | **still open** — depends on delivered `Q`; see §5.2 table | 2026-08-13 |
### 10.4 Needed later, not blocking anything now

7. **Gravity regimes of interest** — which values beyond 1 g, and what is the physical context
   (spaceflight, lunar/Mars surface, centrifuge)? Drives whether `g = 0` exactly is needed.
   Phase 3 only.
8. **What decides "good"?** Uniformity of velocity over the tray? A minimum air speed at
   canopy level? ACH? Temperature spread? The objective function should be defined before
   optimising anything. **Now answerable in concrete terms** — the metric surface is the
   0.014375 m² tray top at Z = 2.5 cm.
9. Is the chamber sealed or leaky? Affects whether inlet/outlet fluxes must balance exactly.
10. **Wall thermal BC** — adiabatic, or does the enclosure lose heat to the room? Matters more
    than usual here because the LED heats the ceiling (§6.3): if the walls are adiabatic, the
    warm cap has nowhere to go.
11. **Tray/substrate surface temperature** — evaporative cooling makes it colder than the air,
    which *strengthens* the stable stratification. Phase 2 sensitivity at minimum.

---

## 11. Quick command reference

```bash
. /usr/lib/openfoam/openfoam2606/etc/bashrc  # activate (required in every shell/script)
#   NOT `. /usr/bin/openfoam2606` -- that execs an interactive session, see 2
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
