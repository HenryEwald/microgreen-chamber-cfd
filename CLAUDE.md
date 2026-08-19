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

> ### ⚠ MEASURED 2026-08-17 — do NOT pair two cases across the CCDs. It is a net LOSS.
>
> `scripts/run_diffuser_screen.sh` offers `FOAM_CPUSET=0-7 ./Allrun & FOAM_CPUSET=8-15 ./Allrun &`
> as a way to double throughput. It does not. Measured on two ~490 k-cell `pimpleFoam` cases,
> 8 ranks each, doing **the same work per step** (8.00 vs 8.15 PIMPLE outer iterations, so the
> comparison is clean):
>
> | | s/step | steps/s |
> |---|---|---|
> | `p1d_casc30_m0` alone, CCD0 | 1.920 | **0.521** |
> | same case, CCD0, while CCD1 is busy | 3.077 (**1.60× slower**) | 0.325 |
> | `p1d_rad15_m0` on CCD1, concurrently | 5.217 | 0.192 |
> | **paired total** | | **0.517** |
>
> **0.517 against 0.521 — pairing buys nothing at all**, and costs the incumbent a 1.60×
> slowdown. Two independent causes, both in this file already: the machine is
> memory-bandwidth bound (§3.2 opening), and **CCD1 is 1.70× slower per step than CCD0 for
> this workload** — the clearest measurement yet of what the 96 MB V-cache is worth, since
> both halves ran identical solvers on near-identical meshes.
>
> **Run cases sequentially on CCD0.** Pair only when the second job is not bandwidth-bound
> (post-processing, meshing, rendering).

> **`templates/Allrun` implements this automatically** (since 2026-08-14). It reads the *final*
> cell count from `log.checkMesh` — not the background count — and **halves** the rank count
> from `decomposeParDict` until the 50 k/rank floor is met, only falling back to serial if even
> 2 ranks cannot meet it. Halving keeps the count a power of two so it lands on whole CCD0 core
> groups.
>
> The earlier all-or-nothing version dropped straight from 8 ranks to serial, which threw away
> most of the machine on any mesh between 50 k and 400 k cells: the 380 k-cell `m0` rung failed
> the 8-rank test (needs 400 k) and ran **serial at ~0.97 s/iteration**, against 0.326 s/iter on
> the 4 ranks this table asks for — a **measured 3.0× loss**.

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
- **`purgeWrite 0;` — KEEP EVERY FRAME. Changed from 5 on 2026-08-16.** Disk is still the
  binding constraint, but the decision moved from the template to **generation time**, where it
  can be made with the numbers in front of you instead of discovered afterwards.

  > **Why it changed.** `purgeWrite 5` is not a storage policy, it is an irreversible one: it
  > deletes the history *as the run proceeds*, and the only way back is to resume from the final
  > state and re-run. It cost the diffuser screen's control arm its frames — a 2.77 h run that
  > left 5 usable time directories at 0.5 s spacing.
  >
  > **`writeInterval` moved with it, and was the real bug.** It was a hard-coded `0.5` chosen
  > when `τ` was 7.29 s — 0.069 τ per frame, 96 frames over a 6.6-τ run, perfectly animatable.
  > At the Ø 40 operating point `τ` is 0.71 s and `endTime` 4.69 s, so the same `0.5` gives
  > **nine frames**. This is the **third** constant found sized for a superseded operating
  > point, after `maxDeltaT` (2026-08-15) and the port area (2026-08-16); the pattern is always
  > the same — a quantity that must scale with `τ` or `U_in`, frozen at one flow rate.
  >
  > `generate_case.sh --frames N` (default 60) now sets `writeInterval = endTime/N`, asserts
  > `purgeWrite 0`, and **projects the disk cost before the case is written** — 271 bytes per
  > cell per write, measured on `p1d_ctrl_m0` (382,613 cells, kOmegaSST, binary, including the
  > `*Mean` and `_0` fields), +40 % for Phase 2. It warns when the projection exceeds half the
  > free disk. That makes §3.3's "decide per study, and decide BEFORE the run" enforced rather
  > than advised.
  >
  > Rough cost at m0: **~5.8 GB per 60-frame case.** A 4-case sweep is ~25 GB, which is why
  > `--frames` is a knob and not a constant.

  > **⚠ It also silently makes ANIMATION impossible, and at `m0` the disk argument no longer
  > holds.** `purgeWrite 5` deletes the history *as the run proceeds* — there is no recovering
  > it afterwards, so a 48 s run leaves 2.5 s of frames. Measured 2026-08-15 at m0+`jetRefine`
  > (415 k cells, 8 ranks, binary):
  >
  > | | frames | disk |
  > |---|---|---|
  > | `purgeWrite 5` (current) | 5 of 96 | **0.5 GB** |
  > | `purgeWrite 0`, Phase 1 | 96 | **9.6 GB** |
  > | `purgeWrite 0`, Phase 2 (+`T`, `alphat`, RANS fields ≈ +40 %) | 96 | **13.4 GB** |
  >
  > Against 109 GB free, keeping the full history for **one or two** cases is cheap. It is not
  > cheap for a 4-case Phase 3 sweep (~54 GB), which is presumably what the setting was
  > guarding. **Decide per study, not globally** — and decide *before* the run, because the
  > frames cannot be recovered later.
  >
  > What is worth animating: `U`, `mag(U)`, `T`. **Not `age`** — it solves a *steady* transport
  > equation, so a per-frame `age` answers "what age field would this instant's flow have if it
  > persisted forever", which is exactly the quantity §8.4 removed from the transient config.
  > The 3D ventilation map is a single `age` field on `phiMean`, not a movie.
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
│   └── mesh_independence.md   # ← m0/m1/m2 ladder + the §9.6 acceptance evidence
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

> ### ⚠ MEASURED 2026-08-14 — Phase 1 at `Q` = 5 m³/h is UNSTEADY. `simpleFoam` cannot do it.
>
> `p1_baseline_m1` ran the full 4000-iteration cap without converging. `p` oscillated in a
> 3e-3 … 4e-2 band with a period of roughly 1000–1400 iterations — three full excursions, no
> net descent after ~1800 — and `U` moved in phase with it, so it is the flow field, not the
> pressure solver. Monitored quantities never went flat: tray mean speed ±9.2 %, tray CoV
> ±17.9 %. See `runs/p1_baseline_m1/NOTES.md` and
> `validation/p1_baseline_m1_convergence.png`.
>
> Physically expected in hindsight: a Ø 20 mm port at 4.42 m/s (`Re_port` = 5832) firing into
> a 12 cm box is a **confined jet, and confined jets flap.** §9.7 anticipated exactly this.
>
> > #### ⚠ REFINED 2026-08-15 by the transient — the jet does NOT flap
> >
> > The steady evidence (residuals that would not descend) was read as jet flapping. The
> > time-accurate run says otherwise. Over 14 s of developed flow at `Q` = 1.25 m³/h:
> >
> > | probe | mean \|U\| | swing |
> > |---|---|---|
> > | jet core | 1.1084 m/s | **0.0 %** |
> > | mid-chamber, on axis | 1.0990 | 0.1 % |
> > | off-axis ±30 mm | ~0.026 | 19–32 % |
> > | **hood** | 0.0454 | **74.7 %** |
> >
> > **The jet is steady to four figures.** What is unsteady is the slow recirculation around
> > it, strongest in the hood — a chamber-scale wander at ≈ 10.8–13.5 s (1.5–1.9 τ), with
> > **100 % of the spectral power below 1 Hz and 0 % in the `St ≈ 0.3` jet-column band**.
> >
> > The conclusion that Phase 1 needs `pimpleFoam` is unchanged — the flow *is* unsteady, and a
> > steady solver still cannot converge it. What changes is the mechanism, and therefore what a
> > fix would target: not jet stabilisation, but the recirculation the ports set up. See
> > `doc/animation_recirc/` and `validation/transient_matrix.md`.
>
> **Consequences:**
> - Phase 1 at this flow rate is `pimpleFoam`, not `simpleFoam` — generate it with
>   `scripts/generate_case.sh --transient`. The answer is a time average plus a fluctuation
>   level, never a single converged number.
> - **Do not read a steady Phase-1 run at `Q` = 5 m³/h as a failed setup.** Mesh, BCs, mass
>   balance and every function object were verified good on the run that exposed this.
> - **ANSWERED 2026-08-14 for the bottom rung: `Q` = 1.25 m³/h is unsteady too.** The hope was
>   that the least energetic rung would settle and make Phase 1 a ~20-minute steady run. It
>   does not. Four laminar steady runs — m0 (to **11,150** iterations), m1, m1 `--jetRefine`,
>   plus the kOmegaSST arm — and **none converges**:
>
>   | | `x_res` | p plateau | orders | tray ± |
>   |---|---|---|---|---|
>   | `m0` | 202.5 mm | 1.40e-1 | 0.9 | ±3.0 % |
>   | `m1` | 50.6 mm | 2.70e-1 | 0.6 | ±18.2 % |
>   | `m1 --jetRefine` | 12.7 mm | 1.40e-1 | 0.9 | ±6.5 % |
>
>   Non-monotone in resolution, never within four orders of the 1e-5 target. Refining does not
>   help — it *unmasks*, because coarse cells were damping a real oscillation numerically.
>   **The chamber flaps at both ends of the flow ladder.** See §7 for the full refutation.
>
>   The one arm that "converges" is `kOmegaSST` (2.4 orders), and only because its `ν_t` is 5×
>   molecular and damps the very physics in question (§5.2). That is not a steady flow, it is
>   a smothered one.
>
> - **Consequence: Phase 1 is `pimpleFoam` at every `Q` tested.** Do not spend another steady
>   run looking for a rung that settles. `generate_case.sh` now warns on steady + laminar.
>   ⚠ The claim that once stood here — "the cost is manageable at the bottom rung, ~2.3 h at
>   m1 and ~0.4 h at m0 against 9.1 h at 5 m³/h" — is **wrong and has been retracted.**
>   A lower `Q` is **not** cheaper; the cost is flat in `Q`. See the corrected cost note below.
> - Phase 2 inherits this. A buoyant case that will not converge at 5 m³/h is now the
>   *expected* outcome, not evidence of a BC error — and §6.3's stable stratification is a
>   second, independent reason to expect the same.

> ### Transient cost — `m2` is infeasible, run the transient at `m0`
>
> Projected 2026-08-14 from the template's own measured anchors (2.28 s/step at
> `nCorrectors` 2, Δt 4.9e-4 s at `maxCo` 6), for a 6.6-τ run on 8 ranks:
>
> | | cells | Δt | steps | wall clock |
> |---|---|---|---|---|
> | `m0` | 380 k | 9.8e-4 | 12,245 | **1.6 h** |
> | `m1` | 1.07 M | 4.9e-4 | 24,490 | **9.1 h** |
> | `m2` | 5.97 M | 2.4e-4 | 48,980 | **102 h — 4.2 days** |
>
> **`m2` pays twice:** 5.6× the work per step *and* 2× the steps, because the Courant-limited
> Δt halves with the cells. It cannot carry a time-accurate run on this machine.
> **Transient mesh independence is therefore `m0`/`m1`;** `m2` is for steady work only.
>
> §9.6 measures the justification: at m0 the tray metrics are within 0.3 % / 2.0 % of m1,
> against a temporal fluctuation of ±3.6 % / ±7.9 %. The mesh is not the limiting error.

> ### ⚠ RETRACTED 2026-08-15 — "lower `Q` is cheaper" is wrong. Transient cost is FLAT in `Q`.
>
> This section used to close with: *"Lower `Q` is cheaper too — Δt scales as 1/`U`, so a
> transient at m1 costs 9.1 h at 5 m³/h, 4.6 h at 2.5, and 2.3 h at 1.25."* That is an
> arithmetic error, and it propagated into §10.2 as a reason to prefer `Q` = 1.25.
>
> **It applied the Δt saving and forgot the endTime penalty.** Both scale the same way:
>
> ```
>     steps = endTime / Δt = 6.6·τ / Δt ,     τ = V_air/Q ∝ 1/Q ,     Δt ∝ 1/U ∝ 1/Q
>           = 6.6·(V_air/Q) / (k/Q) = 6.6·V_air/k        ← Q cancels
> ```
>
> A 6.6-τ transient is **the same number of steps at every flow rate**, because a slower flow
> needs a proportionally longer run to see the same number of flow-throughs. Confirmed against
> the generator: `Q` = 5 at m1 gives 24,505 steps, `Q` = 1.25 at m0+`--jetRefine` gives 24,546
> — the same mesh resolution at the port, the same count. **Choose `Q` on physics, never on
> cost.**
>
> #### The bug this exposed: `maxDeltaT` was a constant
>
> Worse than neutral, low `Q` was actively **4× more expensive** than high `Q`, because
> `templates/transient/system/controlDict` shipped a fixed `maxDeltaT 1e-3` sized for
> `Q` = 5 m³/h. Measured 2026-08-15 on the first m0+`--jetRefine` run at `Q` = 1.25: max
> Courant sat at **2.03 against a `maxCo` of 6**, i.e. the clock cap was binding and the
> Courant condition was not. Δt stayed at the `Q` = 5 value while `endTime` grew 4× with τ.
>
> `maxDeltaT` is a cap on how coarsely the **jet** is stepped, so it has to scale with the
> flow like everything else. `generate_case.sh` now sets it from a fixed jet Courant number
> on the port cell:
>
> ```
>     maxDeltaT = 2.6 · h_port / U_in
> ```
>
> 2.6 is not a new number — it is what the template's own measured anchor already used
> (`Q` = 5, m1, `h_port` = 0.833 mm ⇒ 4.9e-4 s), and the expression reproduces that
> 4.901e-4 exactly. `maxCo 6` stays as the safety net for the small near-wall cells.
>
> #### Measured cost, `Q` = 1.25 m³/h, 4 ranks on CCD0 (2026-08-15)
>
> | | cells | `h_port` | Δt | steps | s/step | wall clock |
> |---|---|---|---|---|---|---|
> | `m0` plain | 380 k | 1.667 mm | 3.92e-3 | 12,270 | 3.6 | **~12 h** |
> | `m0` `--jetRefine` | 415 k | 0.833 mm | 1.96e-3 | 24,546 | 3.2 | **~22 h** |
> | `m1` `--jetRefine` | 1.33 M | 0.417 mm | 9.80e-4 | 49,090 | ~5 (proj.) | **~68 h — not affordable** |
>
> Note `--jetRefine` costs **2× the steps as well as +9 % cells**, because halving the port
> cell halves the time step at fixed jet Courant. It is not the cheap option the +25 %
> cell-count figure in §7 suggests — that figure is the *spatial* cost only.
>
> The per-step cost is also ~3× the old 2.28 s/step anchor at comparable cells/rank, because
> the anchor predates the `nOuterCorrectors 20` + `residualControl` configuration: the outer
> loop now converges in a measured **11 iterations**, i.e. 22 GAMG pressure solves per step
> against the anchor's 8. That buys the stability documented in `fvSolution` — do not trade
> it back for speed without re-reading why it is there.

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

> ### ⚠ MEASURED 2026-08-14 — at `Q` = 1.25 m³/h `kOmegaSST` solves a **6× more viscous
> chamber**. Its better convergence is an artefact, not a virtue.
>
> Both arms run at m0, `Q` = 1.25 m³/h (`Re_port` = 1458), identical mesh and BCs — only
> `constant/turbulenceProperties` differs. `postProcess -func nutStats` on the RANS arm:
>
> | | value |
> |---|---|
> | molecular `ν` | 1.516e-5 m²/s |
> | volume-average `ν_t` | **7.624e-5 m²/s** |
> | **`ν_eff`/`ν`** | **6.0×** |
> | **effective `Re`** | **1458 → 242** |
>
> At `Re_eff` = 242 the flow is deeply laminar and trivially steady. That is the whole
> explanation for the convergence gap:
>
> | | laminar | kOmegaSST |
> |---|---|---|
> | p residual, orders dropped | 0.9 | **2.4** |
> | p plateau | 1.4e-1 | **4.4e-3** |
> | **tray mean speed** [m/s] | **0.0288** | **0.0545** |
> | tray CoV | 0.952 | 0.593 |
>
> **The 89 % spread on the primary metric is over-diffusion of the jet, not a modelling
> subtlety.** `kOmegaSST` is producing spurious eddy viscosity at a Reynolds number where there
> is no turbulence to model, and the extra `ν_t` also thickens the shear layer by √6 = 2.45×,
> which is why the RANS arm tolerates a mesh that cannot resolve the real one (§7).
>
> **Consequences:**
> - **At `Q` = 1.25 m³/h the laminar arm is the physically defensible one.** Do not read
>   `kOmegaSST`'s clean residuals as evidence it is the better model here — it converges
>   *because* it is wrong.
> - The 89 % spread dwarfs both the mesh error (0.3 %, §9.6) and the temporal fluctuation
>   (±3.6 %). **Model choice is by far the largest error bar in the project**, exactly as this
>   section has claimed — now quantified rather than asserted.
> - Still run both and report the spread. But report *which one you believe and why*, rather
>   than presenting them as equally weighted.
> - `generate_case.sh` warns when `Re_port` < 2300 and a turbulent closure is selected.

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
| Tray | — | **12 × 2.5 × 18⅔ cm** (W × H × D) — **FLUSH WITH ALL FOUR WALLS, fills the entire internal floor** (design change 2026-08-16) | top surface at **Z = 2.5 cm**, area **0.0224 m²**. Was 11.5 × 2.5 × 12.5 cm, area 0.014375 m² |
| Tray side slots | — | **GONE.** Were 2.5 mm each side, open | removed 2026-08-16 — see the box below |
| Tray end gaps | — | **GONE.** Were 3.08 cm each end, open | ditto |
| Total internal volume | — | **2.890 L** = 2.165 box + **0.724 hood** | verified numerically; unaffected by the tray |
| Free air volume | `V_air` | **2.3296 L** [2.3296e-3 m³] — tray displaces 0.560 L | the ACH and residence-time denominator. **Was 2.530 L** |
| Coordinate convention | — | X = 12 cm width, Y = 18⅔ cm depth, **Z vertical, −Z down** — **confirmed** by the 1 g assumption | `constant/g` = `(0 0 -9.81)` |
| Units in STL | — | `TBD` | CAD is usually mm; OpenFOAM is **m**. `scale 0.001` in snappy |

> ### ⚠ DESIGN CHANGE 2026-08-16 — the tray is FLUSH and fills the whole floor
>
> The tray was an inset 11.5 × 2.5 × 12.5 cm box with 2.5 mm open slots down each side and
> 3.08 cm open gaps at each end. **All of that is gone.** It is now 12 × 2.5 × 18⅔ cm — the
> full internal footprint, flush against all four walls, a solid block.
>
> | | was | now |
> |---|---|---|
> | tray footprint | 11.5 × 12.5 cm | **12 × 18⅔ cm** |
> | tray top area (the metric surface) | 0.014375 m² | **0.0224 m²** |
> | tray displaced volume | 0.359 L | **0.560 L** |
> | `V_air` | 2.530 L | **2.3296 L** |
> | `τ` at `Q` = 1.25 m³/h | 7.29 s | **6.71 s** |
> | ACH at `Q` = 1.25 m³/h | 494 h⁻¹ | **537 h⁻¹** |
> | m0 cell count | 380 k | **261 k** |
>
> **Consequences that are not just arithmetic:**
>
> - **The `floor` patch no longer exists.** The tray covers the floor completely, so `floor`
>   has zero fluid faces and **snappy drops it from `constant/polyMesh/boundary` entirely.**
>   The bottom of the fluid domain *is* the tray top; the floor is effectively raised to
>   z = 25 mm. Verified: `yPlus` reports `walls`/`hood`/`tray` only, and does not error. The
>   `0.orig` BCs are regexes — `"(floor|walls|hood|tray)"` — so a non-matching alternative is
>   harmless and **no BC file needed changing.**
> - **The tray now carries surface layers** (4, matching the walls; measured 3.97 achieved at
>   85.3 % coverage, better than the walls' 70.1 %). It carried `nSurfaceLayers 0` only because
>   layers could not be inserted inside a 6-cell-wide slot. **Tray wall shear is reportable for
>   the first time** — but only on flush-tray cases; every run generated before this date is
>   still unlayered there.
> - **`m0` no longer needs its level-3 tray override.** That existed solely to stop snappy
>   sealing the 2.5 mm slots. Dropping it takes m0 from 380 k to **261 k cells**.
> - **The headline tray metric is not comparable across the change.** `trayPlane` now averages
>   over 0.0224 m² *including the near-wall boundary layers*, where the old 0.014375 m² window
>   sat entirely in the chamber interior. Expect a **lower** mean speed on the flush geometry
>   for that reason alone. Do not compare it like-for-like with the Phase 1 headline
>   0.02947 m/s (§10.3).
> - **Every result in `runs/` and `validation/` predates this** and describes the slotted
>   geometry. They are not wrong, they are answers about a different chamber. `validation/*.md`
>   deliberately keeps its original `V_air` = 2.5302e-3 figures for that reason.
>
> **Meshing trap, found and fixed 2026-08-16.** The tray STL is written **1 mm oversize** in x,
> y and downward in z, so its sides and base are buried in the wall material instead of exactly
> coplanar with it — coincident surfaces leave snappy's snap direction undefined and the usual
> outcomes (a leak, or a zero-thickness sliver) both pass `checkMesh`. That is correct and
> necessary, **but it means every edge of `tray.stl` now lies inside solid.** Leaving
> `tray.eMesh` in snappy's `features` list made explicit feature snapping pull mesh points out
> onto those buried edges, producing a skirt of cells 1 mm past the chamber walls: patch
> bounding boxes spanning x = −0.001…0.121 against an internal width of 0…0.120, and a total
> volume of 2.3300881e-3 m³ against `V_air` 2.3296e-3 — a **0.49 mL excess**, which is exactly
> perimeter (0.6133 m) × 1 mm × ~0.8 mm. **`tray.eMesh` is deliberately absent from
> `features`; do not add it back.** With it removed the tray patch bounding box is exactly
> (0 0 0.025) → (0.12 0.186667 0.025) and total volume is 2.3292652e-3 (−0.34 mL, ordinary
> surface discretisation).
>
> The real feature — the concave corner where the tray top meets each wall — is an
> intersection of two `refinementSurfaces`, which snappy resolves from the surfaces themselves.

**Terminology — "canopy" is overloaded in this project.** Use **hood** for the curved chamber
lid (this section) and **plant canopy** for the vegetation (§6.5). Patch names: `hood`,
`walls`, `tray`, `plantCanopy`, `inlet`, `outlet` — **`floor` is defined in the geometry but
has no faces in a flush-tray mesh** (see the box above).

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
           ⚠ NO FLUID HERE since 2026-08-16 — the flush tray fills 0.00→2.50 cm
             across the whole footprint, so the `floor` patch has zero faces and
             the fluid domain BEGINS at 2.50 cm
  2.50 cm  tray top   ← growing surface, all metrics evaluated here, 0.0224 m²
             ALSO the bottom wall of the fluid domain
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
| Fan | — | **Sunon MF50100V2-1000U-A99** — 50 × 50 × 10 mm DC axial, 5 VDC, 0.085 A, **430 mW**, 4800 rpm, Vapo-bearing, 25.6 dB(A) — **changed 2026-08-16** | was LD3007MS (30 × 30 × 7 mm). Mounted over a **Ø 40 mm** port |
| Fan rating | `Q_free` | **18.69 m³/h (11.0 CFM) free air; 27.4 Pa (0.110 in-H₂O) shut-off** | a **flow** upgrade, not a **pressure** one — 27.4 Pa is the same class as the part it replaces, because that is what axial fans are |
| Operating flow | `Q_op` | **DERIVED, not chosen — 11.77 m³/h at Ø 40 mm.** `generate_case.sh` solves the fan curve against the system curve; `--Q` overrides and warns | was `TBD`/1.25 m³/h. Still a placeholder in the sense that `K_sys` = 2.5 and the fan mid-curve are estimates — **measure it** (§10.2 item 1) |
| Inlet bulk velocity | `U_in` | `Q / A_port`, `A_port` = 3.1416e-4 m² ⇒ **4.42 / 2.21 / 1.10 m/s** | let `flowRateInletVelocity` compute it; do not hard-code |
| Chamber bulk velocity | `U_bulk` | `Q` / mid-plane free area (**124.8 cm²** = 116.0 box + 38.8 hood − **30.0** tray) ⇒ **0.111 / 0.056 / 0.028 m/s** | 40× slower than the jet — see the `Ri` note. Tray term was 28.75 cm² pre-2026-08-16 |
| Air changes per hour | ACH | `Q` ÷ **2.3296 L** ⇒ **2146 / 1073 / 537 h⁻¹** | enormous, but normal for a 2.33 L box. Was 1976 / 988 / 494 |
| Mean residence time | `τ` | **1.68 / 3.35 / 6.71 s** | the `age` function object should converge near this; much higher ⇒ dead zones. **Was 1.82 / 3.6 / 7.3** — the flush tray displaces 0.2 L more air |
| Port Reynolds number | `Re_port` | `= 1319 · U_in` ⇒ **5 830 / 2 915 / 1 450** | **turbulent / transitional / laminar.** The turbulence model is *not* settled — see §5.2 |
| Fan curve (Δp vs Q) | — | **`TBD` — needed** | LD3007MS datasheet; enables a `fan`/`fanPressure` BC and an actual operating-point prediction |
| Inlet turbulence intensity | `I` | `TBD` [5 %] | fan outlet, no stub to develop in; 5–10 % is the usual range |
| Inlet turb. length scale | `l` | `TBD` [0.07 · D_in = **1.4 mm**] | |
| Operating pressure | `p_op` | `TBD` [101325 Pa] | `pRef` in `fvSolution` |

> ### ⚠ DESIGN CHANGE 2026-08-16 — new fan, Ø 40 mm ports, and an inlet vane diffuser
>
> Full record in `doc/diffuser/design.md`; the geometry is built and meshed, **nothing is
> solved yet**. Headlines:
>
> | | was | now |
> |---|---|---|
> | fan | LD3007MS, 5 m³/h free air | **Sunon MF50100V2**, 18.69 m³/h free air, 27.4 Pa |
> | port | Ø 20 mm | **Ø 40 mm**, both ends |
> | `Q` | 1.25 m³/h (placeholder) | **11.77 m³/h (solved from the fan curve)** |
> | `U_in` | 1.105 m/s | 2.60 m/s |
> | `Re_port` | 1 458 — **laminar** | **6 863 — turbulent** |
> | `U_bulk` | 0.028 m/s | **0.262 m/s** |
> | `τ` | 6.71 s | **0.71 s** |
> | m0 cells | 261 k | **383 k** (control), 500 k (diffused) |
>
> **Three consequences that are not arithmetic:**
>
> 1. **`Re_port` is now turbulent, so `kOmegaSST` is defensible on its own terms.** That
>    removes the project's largest error bar — §5.2's measured **76 % laminar-vs-RANS spread**
>    on tray mean speed existed because `Re_port` = 1458 was below any closure's validity. Note
>    `Re = 4Q/(πDν)` is near-constant across port size here, because `Q` rises roughly linearly
>    with `D` off this fan.
> 2. **The transient is ~4× CHEAPER — ~5 h/case, not ~20 h.** §5.1's "cost is flat in `Q`"
>    identity assumes a **fixed port**. Steps ∝ endTime/Δt ∝ (1/`Q`)/(1/`U`) = `U`/`Q` ∝ 1/`A`,
>    and quadrupling `A_port` raises `Q` 9.4× but `U_in` only 2.35×. This is what makes a
>    4-case diffuser screen affordable at all.
>
>    > #### ⚠ MEASURED 2026-08-17 — true for the CONTROL only. A DIFFUSED case costs 12.6–20.4 h.
>    >
>    > The identity above is arithmetic about the **port**, and it silently assumes the port
>    > cell stays the smallest cell in the mesh. Adding a diffuser breaks that: level-4
>    > `refinementSurfaces` on the vanes puts 0.417 mm cells in the **fastest flow in the
>    > domain**, and Courant ∝ `U`/Δx then re-imposes a limit the port scaling knows nothing
>    > about. `maxCo 6` binds instead of `maxDeltaT`, and Δt collapses:
>    >
>    > | case | vanes | Δt | binds on | steps to 6.6 τ | measured |
>    > |---|---|---|---|---|---|
>    > | `p1d_ctrl_m0` | none | 8.333e-4 | `maxDeltaT` (jet Co 2.6) | 5,647 | **2.77 h** ✓ ~5 h claim |
>    > | `p1d_casc30_m0` | 5, cascade | 2.034e-4 | **`maxCo`** | 23,697 | **12.6 h** |
>    > | `p1d_rad15_m0` | 12 + Ø 12 hub | 1.260e-4 | **`maxCo`** | 38,245 | **20.4 h** (proj.) |
>    >
>    > **The radial concepts are ~1.6× the cascade** because 12 vanes plus a Ø 12 mm hub block
>    > far more of the bore than 5 plates, so the passage runs faster. **A 4-case screen is
>    > ~53 h, not ~20 h.**
>    >
>    > **This cost is REAL and there is no numerics fix.** Measured on the `CourantNo` field at
>    > t = 1.044 s, against the completed control as the reference for what this project has
>    > already accepted:
>    >
>    > | volume fraction above | ctrl @ its Δt | casc30 @ its Δt | casc30 if `maxDeltaT` bound |
>    > |---|---|---|---|
>    > | Co > 3 | 0.00133 % | 0.0120 % | **1.371 %** |
>    > | Co > 4 | **0 %** | 0.00138 % | **0.935 %** |
>    > | Co > 6 | **0 %** | 0 % | **0.293 %** |
>    > | max Co | 3.03 | 6.00 | **25.11** |
>    >
>    > Raising `maxCo` to "restore the `maxDeltaT` design intent" would put ~1 % of the domain
>    > at Courant numbers the control never reaches anywhere, concentrated in the vane passage
>    > that is the object of the study. Note casc30's *volume-weighted mean* Co is 0.114 against
>    > the control's 0.230 — **the constraint is the tail, not the mean.**
>    >
>    > Refinement cannot buy it back either, because the high-Co cells are spread through the
>    > passage rather than piled at one feature — 72 % of the Co > 2 cells sit at r < 19 mm,
>    > inside the bore between the vanes:
>    >
>    > | change | Δt gain | verdict |
>    > |---|---|---|
>    > | shroud only, level 4 → 3 | **1.06×** | useless |
>    > | whole diffuser, level 4 → 3 | **2.00×** | 1.5 mm vane on 1.8 cells — the §7 tray-slot pathology, applied to the feature under study |
>    >
>    > **So the only remaining levers are scope, not numerics:** drop a concept, or screen at
>    > level 3 and confirm the winner at level 4. Cutting `endTime` is not one of them — see
>    > the record-length lesson in §10.3.
> 3. **The chamber CANNOT be over-ventilated.** `U_bulk` = 0.8 m/s would need 35.9 m³/h, far
>    beyond this fan at any port size. So the only way to exceed the 0.8 m/s ceiling anywhere
>    is a surviving jet core, and the only way to reach 0.3 m/s everywhere is piston-like flow.
>    **That is the entire diffuser brief: jet → plug.**
>
> **The port size is not settled.** Ø 45 gives `U_bulk` = 0.294 m/s, landing on the 0.30 m/s
> target exactly, against 0.262 at Ø 40. Ø 40 was chosen because it maximises the *jet-decay*
> figure of merit `Q/D` — the criterion the diffuser exists to make irrelevant — and because it
> leaves 10 mm to the hood spring line where Ø 50 leaves 5 mm and Ø 55 breaks out of the box
> section. **If the diffuser works, revisit this**; `--portD 45` is a one-word change.
>
> **Everything in `runs/` and `validation/` before this date is a Ø 20 mm chamber.**
> `validation/audit_cases.sh` now byte-compares `chamber.stl` as well as `tray.stl` — the port
> change leaves `tray.stl` **identical**, so the tray-only check would have passed 11 cases
> that describe a different chamber.

> ### ⚠ 5 m³/h is free air — the chamber will not see it (LD3007MS, superseded 2026-08-16)
>
> Kept because the *reasoning* is what justified the Ø 40 port: the fix for a fan that cannot
> push against back-pressure is to remove the back-pressure, and Δp ∝ D⁻⁴ makes the port the
> lever. The Sunon has the same 27.4 Pa shut-off, so this argument still binds.
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
> > #### ⚠ 2026-08-15 — the whole table above is at `Q` = 5 m³/h. The working `Q` is 1.25.
> >
> > `ΔT` scales as **1/`Q`**, and the working flow rate moved to 1.25 m³/h on 2026-08-14
> > (§10.2) *after* this table was written. Every figure above is therefore **4× optimistic**
> > for the current default, and the two working placeholders compound badly:
> >
> > | `Q` | `ΔT`/`P` | 38.4 W (the working LED value) | **`P` for a 3 K rise** |
> > |---|---|---|---|
> > | 5 m³/h | 0.60 K/W | 22.9 K ⇒ 43 °C | **5.0 W** (≈ 7 % duty) |
> > | 2.5 | 1.19 | 45.8 K ⇒ 66 °C | 2.5 W |
> > | **1.25 (working)** | **2.39** | **91.7 K ⇒ 112 °C** | **1.3 W — ≈ 1.7 % duty** |
> >
> > **At the working operating point the panel ceiling is ~1.3 W, not ~8 W** — about 1.7 % of
> > the WS2812B's 76.8 W full-white draw. The default pair (38.4 W, 1.25 m³/h) overshoots the
> > 22–25 °C band by roughly **30×** on power.
> >
> > This does not change the plan — Phase 2 still characterises flow structure and
> > stratification usefully, and absolute temperatures were already flagged as
> > non-predictive. It does sharpen the conclusion: **the binding design problem is thermal,
> > not fluid-dynamic.** If the real duty is anywhere near 50 %, no amount of flow-field work
> > rescues it; the chamber needs far more airflow, active cooling, or a much dimmer panel.
> >
> > `generate_case.sh` now prints this as a `!! THERMALLY NON-VIABLE` warning at generation
> > time, with the per-`Q` ceiling, so it cannot be discovered after a run instead of before.
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

> **⚠ MEASURED 2026-08-14 — the warning above is pessimistic.** `p1_baseline_m1`, at the
> *worst case* for this (m1, the coarsest mesh, and `Q` = 5 m³/h, the highest flow):
>
> | patch | max `y⁺` | area-average `y⁺` |
> |---|---|---|
> | floor | 1.42 | 0.35 |
> | walls | 6.06 | 0.77 |
> | hood | 1.27 | 0.49 |
> | tray | 4.92 | 1.24 |
>
> Almost the whole wall area is **below `y⁺` = 1**, i.e. in the viscous sublayer, not the
> 1–30 buffer band. m2 halves the cell size so it will sit lower still, and any `Q` below
> 5 m³/h lowers it further. The blended wall functions are well-behaved in this regime.
>
> This is not licence to stop checking — it is one mesh at one flow rate, and the surface
> layers are what put it there, so a change to `nSurfaceLayers` or the expansion ratio moves
> it. Keep running the `yPlus` FO. But the "worst place to be" concern should not be carried
> into Phase 2 write-ups as though it were still expected.

- Background block: **isotropic cells**, aligned to the box axes. **Base cell = 10/3 mm and
  its halves** (and, for the `m0` rung only, its double — see below) — every internal
  dimension (120, 96⅔, 186⅔ mm, and 146⅔ mm if the hood sits on
  top) is an exact multiple of 10/3 mm, so `blockMesh` divides cleanly with no stray sliver
  cells at the far walls.

  Full internal height is **14⅓ cm = 43 base cells at m1** — exact, since 29/3 + 14/3 = 43/3 cm.

  **⚠ `m1` is the coarsest EXACT mesh — measured 2026-08-14.** The internal dims are
  360 / 560 / 430 thirds-of-a-mm and their GCD is **10**, i.e. 10/3 mm = the m1 base is the
  *largest* base cell that divides all three exactly. No coarser rung can be exact. That is
  fine — `m0` takes 19 × 29 × 23, giving a z cell of 6.522 mm against 6.667 mm in x and y, a
  2.2 % anisotropy (aspect ratio 1.02). The background patch is entirely consumed by snappy
  and the hood is a curved surface that never lay on a cell boundary at any level anyway.

  | Level | Base cell | Background (incl. 1-cell margin) | Final cells | Steady 4000 iter |
  |---|---|---|---|---|
  | `m0` | 6.667 mm | 19 × 29 × 23 = 12.7 k | **261 k** (measured, flush tray) | 21.6 min at 380 k, 4 ranks |
  | `m1` | 3.333 mm | 38 × 58 × 45 = 99 k | **1.07 M** (measured) | **55.7 min**, 8 ranks |
  | `m2` | 1.667 mm | 76 × 116 × 90 = 793 k | **5.97 M** (measured) | ~5.2 h, 8 ranks (proj.) |
  | `m3` | 0.833 mm | 152 × 232 × 180 = 6.35 M | **~33 M** (extrapolated) | ⚠ **NOT BUILDABLE** |

  **The independence ladder is `m0`/`m1`/`m2`, running DOWNWARD** (linear ratios `r` = 1.41 and
  1.77, both clearing the `r ≥ 1.3` that GCI wants). See `validation/mesh_independence.md`.

> ### ⚠ OBSOLETE 2026-08-16 — `m0`'s level-3 tray override is REMOVED (flush tray)
>
> Kept because the lesson generalises and is still the only guard against this class of error.
>
> Measured 2026-08-14, when the tray still had 2.5 mm side slots. At the template's level 2 the
> local cell at m0 is 1.667 mm and the slots got 1.5 cells across — **snappy sealed them both.**
> It was a clean `Mesh OK`, and the *only* symptom was the total volume:
>
> | | total volume | vs `V_air` = 2.5302e-3 m³ |
> |---|---|---|
> | m0, tray level 2 | 2.5147e-3 m³ | **−15.5 mL** |
> | the two tray slots | 1.56e-5 m³ | **15.6 mL — 99 % of the deficit** |
> | m0, tray level 3 | 2.53008e-3 m³ | −0.12 mL ✓ |
>
> Level 3 restored the flow path at 205 k → 380 k cells, and `generate_case.sh` applied it
> automatically for `--mesh m0`. **The flush tray has no slots to seal, so the override is gone
> and m0 is back to level 2 at 261 k cells.**
>
> **The habit survives, and it is now the ONLY guard: always check total volume against
> `V_air`, not just `Mesh OK`.** A sealed feature is invisible to every other mesh metric. It
> also did not fail fast — the run died at the *first write*, when `traySlotFlux` sampled a
> plane that had no faces, long after the solve looked healthy. `templates/Allrun` does this
> check; the same discipline caught the 0.49 mL feature-snapping skirt on the flush tray (§6.1).

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
> ### ⚠ CORRECTED 2026-08-14 — the refinement regions are NOT where the cells are
>
> This section previously claimed `traySlots` was "the worst offender" and that replacing its
> single box with two thin boxes hugging the slots "would cut the count substantially".
> **Both claims are wrong.** The change was made and measured, in a controlled A/B where the
> two `snappyHexMeshDict`s differ *only* in that block (`diff runs/p1_baseline_m1
> runs/p1_transient_m1`):
>
> | | after shell refinement | final |
> |---|---|---|
> | one box | 960,306 | 1,069,964 |
> | two boxes | 956,859 | 1,064,691 |
> | **saving** | **3,447 (0.36 %)** | **5,273 (0.49 %)** |
>
> The single box *looked* expensive because it is geometrically large, but most of its volume
> is **inside the tray solid**, where snappy deletes the cells at the subsetting step
> regardless. Refining cells that are about to be discarded costs almost nothing.
>
> **Where the cells actually are** (m1, from `log.snappyHexMesh`):
>
> | stage | cells | Δ |
> |---|---|---|
> | background | 99 k | |
> | + feature refinement | 130 k | +31 k |
> | **+ surface refinement** | **661 k** | **+531 k ← dominant** |
> | + shell refinement (the boxes) | 960 k | +299 k |
> | − subsetting (drop outside-chamber) | 768 k | −192 k |
> | **+ layers** | **1,070 k** | **+302 k, i.e. +39 % of the pre-layer mesh** |
>
> So the only two real levers are **`refinementSurfaces`** and **`addLayersControls`**, and
> both trade against wall-resolved physics — they are a scientific call, not free
> optimisation. Do not expect `refinementRegions` edits to buy headroom. The two-box version
> is kept because it is the honest description of the intent, not because it is cheaper.
- Ø 20 mm port ⇒ **12 cells across the port at m2**, 24 at m3, before refinement. Level 2 on
  the port walls gives 48 at m2 — enough to resolve the jet that sets the whole flow field.

> ### ⚠ MEASURED 2026-08-14 — "cells across the port" is the wrong criterion for a LAMINAR run
>
> Cells across the *port* says nothing about cells across the **shear layer**, and the shear
> layer is what a laminar run has to resolve. The ports are plain cutouts carrying a top-hat
> inlet BC (§6.1/§6.2), so the layer starts at **zero thickness on the lip** and grows as
> `δ ~ √(νx/U)`. It is resolved once `δ ≥ h`, i.e. beyond
>
> ```
>     x_res = h² · U / ν          h = cell size at the port = base/4 at level 2
> ```
>
> At `Q` = 1.25 m³/h (`U` = 1.105 m/s), against the 186.7 mm inlet→outlet path:
>
> | mesh | `h` at port | `x_res` | verdict |
> |---|---|---|---|
> | `m0` | 1.667 mm | **202.5 mm** | **NEVER resolved in-domain** |
> | `m1` | 0.833 mm | 50.6 mm | resolved over the last 73 % |
> | `m2` | 0.417 mm | 12.7 mm | resolved over the last 93 % |
>
> ### ⚠ This criterion is REAL but it is NOT why the steady laminar run stalls
>
> An earlier version of this section claimed the unresolved shear layer was "the root cause of
> the stalled laminar run". **That was a hypothesis, it was tested, and it is refuted.**
> Recorded here so nobody re-runs the experiment.
>
> Three laminar runs at `Q` = 1.25 m³/h, everything fixed except mesh resolution — a 16× range
> in `x_res`:
>
> | case | `x_res` | cells | p plateau | orders | tray mean | tray ± |
> |---|---|---|---|---|---|---|
> | `m0` | 202.5 mm | 379,918 | 1.40e-1 | 0.9 | 0.02835 | **±3.0 %** |
> | `m1` control | 50.6 mm | 1,064,691 | **2.70e-1** | 0.6 | 0.02724 | **±18.2 %** |
> | `m1 --jetRefine` | 12.7 mm | 1,334,627 | 1.40e-1 | 0.9 | 0.02625 | **±6.5 %** |
>
> **Refining did not help — it is non-monotone, and m1 is the worst of the three.** None gets
> within four orders of the 1e-5 `residualControl` target.
>
> What *does* behave: the tray **mean** spans only **8 %** across that 16× resolution range,
> i.e. it is mesh-converged. It is the **fluctuation** that moves, and not monotonically —
> because what each mesh really varies is how much *numerical damping* it applies to an
> unsteady flow. m0's apparently-calm ±3.0 % (5 zero crossings) is coarse-cell diffusion
> smoothing a real oscillation; m1 removes that damping and exposes ±18.2 %.
>
> **The flow at `Q` = 1.25 m³/h is genuinely unsteady, exactly as at 5 m³/h (§5.1). A steady
> solver cannot converge it at any resolution.** The `Uy` 2.8e-3 vs `Ux` 2.1e-2 / `Uz` 2.6e-2
> split — streamwise pinned by mass conservation while the cross-stream recirculation wanders
> — is the flapping signature, not an under-resolution signature. GAMG was never the problem:
> it reached a p **final** residual of 5.8e-4 every iteration while the **initial** residual
> stayed at 8.0e-2. Mesh, BCs and iteration count were all eliminated first (`checkMesh` clean,
> volume exact, mass balance **2e-10**, continuity stable, residual flat from iteration 4,533
> to **11,150**).
>
> **So `x_res` tells you what resolution a faithful TRANSIENT needs. It does not predict, and
> cannot fix, steady convergence.** `--jetRefine` is worth having for the transient — it is
> still the cheapest route to m2-grade shear resolution — but do not reach for it expecting a
> steady run to settle.
>
> **`--jetRefine` is the efficient way to BUY shear-layer resolution** — not a convergence fix
> (see the refutation below). It adds one level on a tight box over the first ~26 mm of the
> *inlet* jet only (an outlet is a sink with no shear layer worth resolving, §6.2), quartering
> `x_res`:
>
> | | `x_res` | cells | measured |
> |---|---|---|---|
> | `m1` | 50.6 mm | 1,064,691 | — |
> | **`m1 --jetRefine`** | **12.7 mm** | **1,334,627** | **+25.4 %** |
> | `m2` | 12.7 mm | 5,967,102 | +460 % |
>
> **Same shear-layer resolution as m2 for 4.5× fewer cells.** Verified 2026-08-14: the
> `--jetRefine` mesh passes `checkMesh` with total volume 2.53019e-3 m³ against `V_air`
> 2.5302e-3, i.e. the tray slots stay open and the extra refinement costs nothing in quality.
>
> **This does not apply to the RANS arm** — its `ν_t` is 5× molecular (§5.2), thickening the
> layer by √6 and hiding the problem. That is why `--jetRefine` is opt-in rather than
> automatic: turning it on for both arms wastes cells on the RANS side, and turning it on for
> only the laminar arm would confound the model-spread comparison. `generate_case.sh` prints
> `x_res` for every laminar case and warns when it exceeds the chamber depth.
>
> **Do not "fix" this with `bounded Gauss upwind`.** It would converge, by adding numerical
> diffusion to a jet whose measured problem is already too much diffusion — trading a visible
> failure for an invisible one. See the note in `fvSchemes`.
- **~~The tray side slots are the tightest feature in the mesh~~ — REMOVED 2026-08-16.** The
  tray is now flush with all four walls (§6.1), so there are no slots, no end gaps, and
  nothing below z = 25 mm. The tightest feature in the mesh is now the **port**, and the
  binding resolution criterion is the jet shear layer (`x_res`, above), not a gap width.
  Consequences: the level-2 tray surface refinement is kept but is no longer load-bearing;
  snappy `gap_detection` is not needed; and the tray now takes **4 surface layers** like every
  other no-slip wall, where it previously took none. **Tray wall shear became reportable with
  that change** — measured 3.97 layers at 85.3 % coverage at m0, against 70.1 % on the walls.
  Watch the **tray/wall concave corner** in `checkMesh` instead: that is where two layer
  stacks now collide, and where layer collapse would show up first.
- **~~Sanity-check the slots before trusting them~~ — moot.** The answer, for the record, was
  **≈ 0.23 % of `Q`** (steady m1). That measured a flow path that no longer exists, and the
  `traySlotFlux` function object that produced it has been deleted — it had to be, because a
  `sampledSurface` with zero faces kills the run at the first write.
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
- Mesh independence study is mandatory before any published number — 3 levels, tracked in
  `validation/`. **Done for Phase 1: `m0`/`m1`/`m2`, see `validation/mesh_independence.md`.**
  The ladder runs *downward* because `m3` is not buildable; the cell-count ratios are 2.8×
  and 5.6× (linear `r` = 1.41 and 1.77), comfortably past the ~1.5–2× this line used to ask
  for.

> ### ⚠ MEASURED 2026-08-14 — the mesh is not the limiting error at Q = 5 m³/h
>
> m0 (380 k) vs m1 (1.07 M), averaged over iterations 1500–4000 (~2 oscillation periods):
>
> | metric | m0 | m1 | mesh diff | temporal fluctuation (1σ) |
> |---|---|---|---|---|
> | **tray mean speed** [m/s] | 0.252112 | 0.251422 | **0.3 %** | **±3.6 %** |
> | **tray CoV** (uniformity) | 0.457004 | 0.466248 | **2.0 %** | **±7.9 %** |
> | tray slot flux [m³/s] | −3.878e-6 | −3.153e-6 | 23.0 % | ±12.3 % |
> | slot split, % of `Q` | 0.279 % | 0.227 % | | |
>
> **On the two tray metrics this project reports, the discretisation error between 380 k and
> 1.07 M cells is 4–12× smaller than the unsteadiness it sits inside.** Refining further does
> not buy a better answer — it buys a more precise number for a quantity whose true value
> oscillates by an order of magnitude more. `y+` supports this: area-averages at m0 are
> floor 0.30 / walls 0.74 / hood 0.93 / tray 1.21, all still viscous sublayer.
>
> **Consequence: run the transient at `m0`.** See §5.1 for the cost table.
>
> Four things this does *not* establish, all of which matter:
> 1. **It is not a GCI.** These are SIMPLE-*iteration* averages of a run that never converged,
>    because the flow is unsteady here. Iterations are not time. Strong indicator, not proof —
>    the rigorous version needs transient time-averages.
> 2. **It does not test slot resolution.** m0 and m1 both resolve the slots at 0.833 mm; that
>    was forced, to keep them open at all. Everything *except* the slots is varied.
> 3. **The slot flux is genuinely mesh-sensitive** (23 %). Anything depending on the slots
>    needs m1 or finer.
> 4. **Phase 2 is not covered.** The hood carries the LED load and its `y+` doubles at m0
>    (0.49 → 0.93). Wall heat flux is far more mesh-sensitive than tray velocity — re-check
>    there rather than carrying the m0 verdict across.

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

> **⚠ `age` is the exception — it is a STEADY function object.** It solves a steady transport
> equation on whatever `phi` is current, so firing it at `writeTime` in a transient run answers
> "what age field would this flow have if this instant's velocity persisted forever". On a
> flapping jet successive snapshots disagree and none of them is the answer.
>
> It is therefore **removed from `templates/transient/system/controlDict`** (2026-08-14). The
> mean age is a mean-flow property, evaluated once, post-hoc, on the time-averaged flux — which
> is exactly why `functions/transientMonitors` averages `phi`. Recipe:
>
> ```bash
> cd runs/<case> && ls -d [0-9]*        # pick the final time
> cp <T>/phiMean <T>/phi                # age reads phi
> postProcess -func age -time <T>
> ```
>
> The `age` solver entry stays in `fvSolution`. Secondary benefit: at `writeInterval` 0.5 over
> 12 s that was 24 transport solves per run, all discarded.
>
> > #### ⚠ CORRECTED 2026-08-15 — the `postProcess` recipe above does NOT work. Use the script.
> >
> > ```bash
> > scripts/age_of_air.sh runs/<case>              # phiMean, latest time
> > scripts/age_of_air.sh runs/<case> --field phi --time 4000
> > ```
> >
> > The `cp phiMean phi && postProcess -func age` recipe fails in two independent ways, both
> > verified 2026-08-15:
> >
> > 1. **`-func age` finds no config.** There is no `age` file under
> >    `etc/caseDicts/postProcessing/`, so the utility prints
> >    `Cannot find functionObject file age` — as a *warning* — and **exits 0 having done
> >    nothing**. It fails silently, which is the worst way for it to fail.
> > 2. **`age` cannot run under `postProcess` at all.** `src/functionObjects/field/age/age.C`
> >    line 128, inside `read()`, does
> >    `mesh_.lookupObject<surfaceScalarField>(phiName_)` — so `phi` must already be
> >    **registered when the function object is constructed**. `postProcess` constructs its
> >    function objects *before* reading fields and never auto-loads a `surfaceScalarField`,
> >    so this throws `failed lookup of phi ... available objects of type surfaceScalarField:
> >    0()`. `-fields '(phi U)'` does not help (loads after construction), and
> >    `simpleFoam -postProcess` does not help either (same ordering).
> >
> > `age` therefore has to run **inside a solver**, where `createFields` has registered `phi`
> > and the turbulence model — which is exactly why the in-solver `ageMean` series in the
> > steady runs works fine. `scripts/age_of_air.sh` copies the case to `<case>/ageEval/`, puts
> > `phiMean` in as `phi`, and runs the solver for **one** deliberately tiny step (1e-8 s, or
> > 1 iteration for a steady solver) purely to give the function object a live registry.
> >
> > Watch for a zero-iteration run: `endTime` must be *representably* larger than `startTime`.
> > At t = 4000 an increment of 1e-8 printed with `%.10g` comes back as `4000`, `endTime` then
> > equals `startTime`, and the solver prints `Starting time loop` → `End` having computed
> > nothing while exiting 0. The script formats with `%.16g` and asserts the loop turned over.
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
| 1 | **LD3007MS Δp–Q curve** — 5 m³/h is free air, delivered flow is likely well below it | **`Q` = 1.25 m³/h** as of 2026-08-14 (was 5); still sweep 5 / 2.5 / 1.25 and report everything vs `Q` | §6.2 |
| 2 | **LED duty / brightness** | **38.4 W (50 % white)** — thermally non-viable, see the warning | §6.3 |
| 3 | **Turbulence model at `Q` = 1.25** — `Re_port` = 1458 is **laminar**, but the default is still `kOmegaSST` | run the pair, `--model laminar` and `--model kOmegaSST`, report the spread | §5.2 |

All three are **noted, not resolved.** Item 1 changes the turbulence regime (§5.2) and every
mixing metric; item 2 makes the absolute temperatures unphysical while leaving the flow
structure informative; item 3 follows directly from item 1 and is now live rather than
hypothetical. None blocks Phase 1. Every run's `NOTES.md` must state which working value it
used, and no figure derived from them goes out without the caveat on it.

> **Why the default moved to 1.25 m³/h (2026-08-14).** 5 m³/h is the **free-air** rating at
> zero back-pressure. This chamber presents ≳ 30 Pa (§6.2), at or beyond a 30 mm axial fan's
> likely shut-off, and the fan is blowing into a hole 44 % of its face area — so the delivered
> flow is "plausibly half or less". 1.25 is the bottom rung of the ladder and the most likely
> of the three to bracket the real operating point.
>
> ⚠ **Two of the three original reasons for this default have since been withdrawn**, and the
> choice now rests entirely on the free-air argument above — which is still sound, so the
> default stands. Struck out for the record:
> - ~~"It is also the cheapest to run, by a lot: Δt scales as 1/`U`, so a transient costs
>   2.3 h at m1 against 9.1 h at 5 m³/h"~~ — **wrong, retracted 2026-08-15.** τ scales as
>   1/`Q` too, so the step count is flat in `Q`. See §5.1.
> - ~~"and the flow may well settle *steady* at this rung, which is another ~10× on top"~~ —
>   **tested and refuted 2026-08-14.** It does not settle; the chamber flaps at both ends of
>   the ladder (§5.1, §7).
>
> **This is a better-motivated placeholder, not a measurement.** `generate_case.sh` now warns
> when `Re_port` lands in the laminar or transitional band with a turbulent closure selected.

### 10.3 Resolved

| Question | Answer | Date |
|---|---|---|
| Chamber internal dimensions | 12 × 9⅔ × 18⅔ cm | 2026-08-13 |
| Port size and height | Ø 20 mm, bottom edge Z = 6 cm | 2026-08-13 |
| Hood rise | 0.5 cm lip + 4.5 cm spline = 5.0 cm | 2026-08-13 |
| Port construction | plain circular cutouts, no stubs | 2026-08-13 |
| Port arrangement | one per opposite end face, centred, mirror-symmetric *(inferred)* | 2026-08-13 |
| Tray | ~~11.5 × 2.5 × 12.5 cm box, centred on the floor~~ **SUPERSEDED 2026-08-16: 12 × 2.5 × 18⅔ cm, flush with all four walls, fills the whole floor** | 2026-08-13 |
| LED location | curved over the hood interior ⇒ **stable stratification**, see §6.3 | 2026-08-13 |
| Baseline gravity | 1 g Earth, `(0 0 -9.81)`, −Z down | 2026-08-13 |
| Total internal height | **14⅔ cm** floor → hood peak; **no flat ceiling** | 2026-08-13 |
| Hood profile | **parabola**, `y = 4.5·[1 − ((x−6.3335)/6.3335)²]` external; analytic internal offset | 2026-08-13 |
| Tray side slots | ~~**open** — tray is flush with the floor only ⇒ must be meshed~~ **REMOVED 2026-08-16 — the tray is flush with the walls too, there are no slots** | 2026-08-13 |
| Port Z datum | measured from the **external base** | 2026-08-13 |
| Fan | **LD3007MS**, 5 m³/h **free air** — an upper bound, not the operating point | 2026-08-13 |
| Hood internal surface | 3.33 mm normal offset ⇒ internal height **14⅓ cm**, span 12.0 cm | 2026-08-13 |
| Wall/floor thickness | **3.33 mm** throughout | 2026-08-13 |
| Hood extrusion | straight barrel vault, hollow shell, flat end walls | 2026-08-13 |
| LED panel | **WS2812B 16×16**, 160 × 160 mm, 0.0256 m², max 76.8 W; negligible thickness | 2026-08-13 |
| CAD/STL needed? | **No** — fully parametric `blockMesh` + `snappyHexMesh` | 2026-08-13 |
| Turbulence model | **still open** — depends on delivered `Q`; see §5.2 table | 2026-08-13 |
| **Is the flow steady at `Q` = 5 m³/h?** | **No.** Confined jet flapping; `simpleFoam` will not converge. Use `--transient`. See §5.1 | 2026-08-14 |
| `y⁺` regime | **Viscous sublayer, not the buffer band** — area-averages 0.35–1.24 at m1/5 m³/h. §7's warning is pessimistic | 2026-08-14 |
| Tray side-slot flow split | ~~**≈ 0.23 % of `Q`** (steady m1)~~ **MOOT 2026-08-16** — measured a flow path the flush tray removed. The `traySlotFlux` FO is deleted | 2026-08-14 |
| Concave cells in `checkMesh -allGeometry` | **Accepted, not a defect** — the test flags planar as well as folded cells at a 1e-6 tolerance and is excluded from default `checkMesh`. Max cell openness 5e-16. `Allrun` gates on the standard pass | 2026-08-14 |
| Does the two-box `traySlots` rewrite save cells? | **No — 0.49 %**, not "substantially". Controlled A/B at m1. The cells are in `refinementSurfaces` (+531 k) and layers (+302 k, +39 %). See §7 | 2026-08-14 |
| Coarsest mesh that divides the geometry exactly | **`m1`** — GCD of the internal dims is exactly the m1 base cell. `m0` is 2.2 % anisotropic in z and that is fine | 2026-08-14 |
| Mesh-independence ladder | **`m0`/`m1`/`m2`, running downward** (`r` = 1.41, 1.77). `m3` (~33 M) is not buildable against the 20 M cap | 2026-08-14 |
| Is the mesh the limiting error on the tray metrics? | **No.** m0 vs m1 differ by 0.3 % (mean speed) and 2.0 % (CoV) against ±3.6 % / ±7.9 % temporal fluctuation. Run the transient at m0. See §9.6 | 2026-08-14 |
| Is a transient at `m2` affordable? | **No — ~102 h.** m2 pays 5.6× per step *and* 2× the steps. Transient work is m0/m1 only. See §5.1 | 2026-08-14 |
| Working flow rate | **1.25 m³/h** (was 5). Bottom rung of the ladder; 5 is free air, an upper bound. Placeholder, not a measurement. See §10.2 | 2026-08-14 |
| **Is `Q` = 1.25 m³/h steady?** | **No — the chamber flaps at BOTH ends of the ladder.** 4 steady runs (m0 to 11,150 iters, m1, m1+jetRefine, kOmegaSST), none converges. Phase 1 is `pimpleFoam` at every `Q`. See §5.1 | 2026-08-14 |
| Why does the laminar arm stall at `Q` = 1.25? | **Genuine unsteadiness.** The shear-layer-resolution hypothesis was tested across a 16× `x_res` range and **refuted** — p plateau went 1.4e-1 / 2.7e-1 / 1.4e-1, non-monotone. Mesh, BCs, iteration count all eliminated first. See §7 | 2026-08-14 |
| Does a coarse mesh make the flow look steadier than it is? | **Yes, badly.** m0 reports ±3.0 % tray fluctuation where m1 reports ±18.2 % — coarse-cell numerical diffusion damping a real oscillation. The *mean* is mesh-converged to 8 %; the fluctuation is not | 2026-08-14 |
| Is `kOmegaSST`'s clean convergence at `Q` = 1.25 meaningful? | **No.** Measured `ν_t` = 5× molecular ⇒ `ν_eff`/`ν` = 6, `Re_eff` = 242 not 1458. It converges because it solves a 6× more viscous problem. See §5.2 | 2026-08-14 |
| Largest error bar in the project | **Turbulence model, 89 %** on tray mean speed at `Q` = 1.25 (laminar 0.0288 vs kOmegaSST 0.0545 m/s) — vs 0.3 % mesh and ±3.6 % temporal | 2026-08-14 |
| Is a transient cheaper at low `Q`? | **No — cost is FLAT in `Q`.** τ ∝ 1/`Q` and Δt ∝ 1/`Q` cancel exactly, so a 6.6-τ run is ~24.5 k steps at every flow rate. The old "2.3 h at 1.25 vs 9.1 h at 5" applied the Δt saving and forgot the endTime penalty. **Retracted.** See §5.1 | 2026-08-15 |
| Why was low `Q` actually *more* expensive? | **`maxDeltaT` was a hard-coded 1e-3**, sized for `Q` = 5. At `Q` = 1.25 it bound at max Courant 2.03 against `maxCo` 6, so Δt stayed put while endTime grew 4×. Now set as `2.6·h_port/U_in` — a fixed jet Courant, which reproduces the measured 4.9e-4 anchor exactly | 2026-08-15 |
| Is `--jetRefine` really only +25 %? | **No — that is the spatial cost only.** Halving the port cell also halves Δt at fixed jet Courant, so it is **+9 % cells and 2× the steps** ⇒ ~2.2× the wall clock. §7's "+25 % cells vs +460 % for the next mesh level" is still true and still the right trade, but it is not the whole bill | 2026-08-15 |
| Error bar on a transient time-average | **`sd/√N` is invalid here** — samples are correlated. Monte-Carlo on AR(1): ±2·`sd/√N` covers the true mean **15 %** of the time, against 93 % for `sd/√N_eff` with `N_eff = N·Δt/2T_int`. `validation/compare_transients.py` uses the latter; `validation/test_stats.py` guards it | 2026-08-15 |
| Does the §8.4 `postProcess -func age` recipe work? | **No, and it fails silently.** No `age` caseDict exists (warning + exit 0), and `age.C:128` looks up `phi` at *construction*, before `postProcess` reads fields. Must run inside a solver. Use `scripts/age_of_air.sh` | 2026-08-15 |
| Hard-coded `tau = 1.82 s` in the plotting scripts | Present in **both** `plot_transient.py` and `plot_convergence.py` — correct only at `Q` = 5. At the working `Q` = 1.25 the true τ is 7.29 s, so the transient script over-reported the averaging window **4×** and the convergence script drew the age reference line **4× too low**. Both now read `volumetricFlowRate` from the case's own `0.orig/U` | 2026-08-15 |
| How do you know an age solve converged? | **`<age>_outlet == τ` exactly**, for any steady flow — mass conservation on the age field. Now the `ageOutlet` FO. Measured −0.108 % (limitedLinear) / −0.016 % (upwind). **Do not report an age without it** | 2026-08-15 |
| Is the age solve broken? (1000-iter caps, first solve diverging) | **No — cosmetic.** `limitedLinear`'s solution-dependent limiter changes the matrix each outer pass so the initial residual never contracts, but the identity holds to 0.1 %. Keep `limitedLinear`: `upwind` converges cleanly and is 6.6× closer on the identity, but smears the field and reports age **9.1 % low**. Carry 9 % as the age discretisation uncertainty | 2026-08-15 |
| How well is the chamber ventilated? | **Badly — ε_a ≈ 10 %** (perfect mixing 50 %, piston 100 %). Volume-mean age **4.90 τ**, max **10.75 τ**. Severe short-circuiting. ⚠ **Provisional** — non-converged steady field; supersede with `phiMean` from the transient. See `validation/age_of_air.md` | 2026-08-15 |
| Is the hood the worst-ventilated region, as §6.1 predicts? | **Provisionally NO.** `ageHood` = 4.82 τ against a chamber mean of 4.90 τ — **0.984 of the mean**, not "worst by a wide margin". `ageCanopy` is 4.67 τ, marginally the *best*. The chamber looks **uniformly stale**, not core-plus-dead-cap. ⚠ Same non-converged field, and the gap is smaller than the 9 % scheme uncertainty — **re-check on the transient before amending §6.1** | 2026-08-15 |
| Where IS the dead air, then? | **On the INLET side, along the floor** — not the hood, and not the outlet side. Volume-averaged age falls monotonically from **6.28 τ** in the first 23 mm to **3.96 τ** in the last: air is **58 % older at the inlet end**. The jet entrains as it crosses, sweeping everything downstream toward the exit, while the pocket *beneath the incoming jet* sits in its shadow with no return path. Worst cell ~11 τ in that corner. The tray spans the whole gradient ⇒ **~55 % variation in air age across the crop**. Indicated fix is the **port arrangement** (angle the inlet down, offset the ports diagonally, add a return path), not jet strength. See `doc/ventilation/` | 2026-08-15 |
| **PHASE 1 HEADLINE RESULT** | Tray-plane mean speed **0.02947 ± 0.00018 m/s** (correlated-sample SE, 0.6 %), RMS 2.3 %, `N_eff` = 15, over 3.85 τ of a 6.6 τ transient at `Q` = 1.25 m³/h, m0+`--jetRefine`, laminar. The discard window is **validated, not assumed**: the mean plateaus from ~1.5 τ and moves ±0.3 % out to 4 τ. See `validation/transient_matrix.md` | 2026-08-15 |
| Does the jet actually flap? | **No — the jet is STEADY.** Over 14 s of developed flow the jet core swings **0.0 %** (1.1084 m/s) and the on-axis mid-chamber probe 0.1 %. All the unsteadiness is in the slow recirculation: off-axis ±30 mm swing 19–32 %, and the **hood 74.7 %** on a 0.045 m/s mean. §5.1's "confined jet flapping" framing came from steady runs refusing to converge; the transient shows **a steady jet with a slowly wandering recirculation around it**. Consistent with the spectrum (100 % of power < 1 Hz, 0 % in the `St≈0.3` band) but not the same mechanism | 2026-08-15 |
| Ventilation efficiency, converged | **ε_a = 10.0 %** (perfect mixing 50 %, piston 100 %). Volume-mean age **4.99 τ**, hood 4.87, canopy 4.76, worst cell 11.26. `ageOutlet` = 0.9995 τ, i.e. the identity holds to **−0.047 %** — that is what certifies the solve. Computed on `phiMean`, not a snapshot. See `doc/ventilation/` | 2026-08-15 |
| ⚠ `reconstructPar` with no arguments reconstructs NOTHING | It builds its time list from the **case root**, which on a decomposed case holds only `constant` and `0`, and the default excludes `0` (`-withZero`). It warns `No times selected`, **exits 0**, and `Allrun` prints its acceptance checklist. The laminar run finished with only `0/` reconstructed while `processor*/` held 46–48; nothing said so until post-processing went looking. `templates/Allrun` now derives an explicit `-time first:last` from `processor0` **and asserts a time > 0 exists** | 2026-08-15 |
| ⚠ ParaView renders need the colour scale pinned | `AutomaticRescaleRangeMode` defaults to rescaling per *representation*, so every panel silently gets its own scale — measured, the x-slice came out −0.12…76 and the tray plane 21…68 **from the same field at the same instant**. Set it to `Never`. In an animation the same default makes colour pulse with the normalisation, which reads as motion. `scripts/render_field.py` / `render_animation.py` pin it | 2026-08-15 |
| Choosing an animation colour scale | **Linear is wrong when a fast jet and a slow recirculation share the frame.** Jet 1.108 m/s at 0.0 % swing vs hood 0.045 m/s at 74.7 %: on a linear 0–1.3 ramp all the unsteadiness sits in the bottom 3 % and the animation looks static. Clip the scale (0–0.08 m/s here) so the jet saturates and the slow field gets the full ramp. Both versions kept in `doc/animation_jet/` and `doc/animation_recirc/` | 2026-08-15 |
| SMT oversubscription via `FOAM_CPUSET` | `FOAM_CPUSET=0-3` on a case the 50 k floor sized at **8 ranks** packed 8 ranks onto 4 cores: **7.0 s/step vs 2.94 properly placed, a 2.4× loss**, silently. `templates/Allrun` now measures the cpu-set width and refuses to launch if it is narrower than the rank count | 2026-08-15 |
| Does the Phase 2 / 2b buoyant solver path actually run? | **It did not — `rhoFinal` was missing from the transient `fvSolution`.** `buoyantPimpleFoam` died on time step 1: PIMPLE needs `<field>Final` for every field it solves, and `rho` was a bare entry matching neither `p*Final` nor the `"(U\|k\|omega\|e\|h)Final"` regex. **Phase 1 cannot expose this** — `pimpleFoam` is incompressible and never solves `rho`. Now `"rho.*"`. Found by a deliberate 0.03-τ smoke test; without it the whole Phase 3 sweep would have produced zero time steps | 2026-08-15 |
| *How* does `kOmegaSST` get its clean convergence? | ⚠ **RETRACTED 2026-08-15.** A matched-time window at 1.04–1.31 τ showed the laminar jet flapping (`r` = −0.36) while the RANS jet was symmetric (`r` = +0.999), suggesting the closure *removes* the instability. **The matched repeat at 1.92–2.19 τ reversed it** (+0.581 vs −0.997). Probe correlation on a 2 s window tracks the phase of a ≥ 8.9 s oscillation, not the presence of one. **Not established.** What survives: the tray mean spread is **~110 %** (+117 %, +107 % at two windows). See `validation/transient_matrix.md` §4a |  2026-08-15 |
| Is the unsteadiness a jet-column instability (`St ≈ 0.3`)? | **No.** That mode would sit at 16.6 Hz; measured, the 5–30 Hz band holds **0.0 %** of the power against **100 %** below 1 Hz, with Nyquist at 255 Hz so the band is well resolved. It is a **chamber-scale recirculation, period ≈ 10.8 s ≈ 1.5 τ** (resolved on a 21.5 s record; order-of-magnitude). `functions/transientMonitors` is corrected. **The binding constraint is RECORD LENGTH, not sample rate** — 6.6 τ gives only ≈ 2.6 cycles | 2026-08-15 |
| Is `bounding k` in the RANS arm a problem? | **No, when it is flat.** The kOmegaSST arm emits ~11,000 `bounding k` messages; `max(k)` sits at ~0.054 for the whole run and the clipped `min` is **positive** (3e-16, below `kMin`) — the solver is flooring near-zero `k` in cells where turbulence has decayed, expected at `Re_port` = 1458. Distinguish from the documented divergence (`k` → 1e105) by checking whether `max(k)` **grows**, not by counting messages. See `validation/transient_matrix.md` §4a-bis | 2026-08-15 |
| ⚠ Statistics on short windows | **A statistic computed over a window shorter than the flow's own timescale reports the window, not the physics.** Bit this project twice in one day: the spectral peak sat at `1/T` for every record length tried, and probe correlation `r` swung +0.99 → −0.99 → −0.13 across successive 2 s windows against a ≥ 8.9 s timescale. The `r` version produced a plausible result **agreeing with the §5.2 prior**, which is why it was believed. Withdrawn: "flapping onsets at 1.05 τ" and "kOmegaSST suppresses the instability" | 2026-08-15 |
| Do old cases in `runs/` drift after a template fix? | **Yes, silently.** `p1_transient_m1` predates the `maxDeltaT` fix and still carries `1e-3` where 4.901e-4 is correct — it would step **2× too coarse in the jet** while reporting a comfortable max Courant, because `maxCo 6` is never reached. `validation/audit_cases.sh` checks every case against what the current generator would produce, and exits 1 if any is stale. **Extended 2026-08-16 to byte-compare each case's `tray.stl` against a freshly generated one** — after the flush-tray change 11 of 13 cases describe a different chamber, and nothing else says so. Regenerate rather than hand-edit (§1.3) | 2026-08-15 |
| Are the sweep drivers usable as written? | **No — both rewritten.** `sweep_gravity.sh` and `sweep_Q.sh` were **steady, on `m2`, kOmegaSST by default**; every case would have failed to converge at ~5 h each. Now `m0 --jetRefine --transient`, model from `Re_port`, with cost warnings and `GVALS`/`QVALS`/`MESH` env overrides. See §10.4 | 2026-08-15 |
| LED ceiling at the **working** `Q` | **~1.3 W, not ~8 W.** §6.3's table is at `Q` = 5; `ΔT` ∝ 1/`Q` and the working `Q` is 1.25, so the default pair (38.4 W, 1.25 m³/h) gives **ΔT = 91.7 K ⇒ 112 °C** — ~30× over budget, not the 43 °C the table implies. `generate_case.sh` now warns at generation time. **The binding design problem is thermal, not fluid-dynamic** | 2026-08-15 |
| ⚠ Do transient runs keep enough frames to animate? | **They do now — `purgeWrite 0`, `writeInterval = endTime/--frames`, from 2026-08-16.** Previously `purgeWrite 5` deleted the history as the run proceeded (irreversible), and `writeInterval` was hard-coded at 0.5 s — 96 frames at `τ` = 7.29 s but **nine** at `τ` = 0.71 s. Third constant found frozen at a superseded operating point, after `maxDeltaT` and the port area. `generate_case.sh` now projects the disk cost (271 bytes/cell/write, measured) and warns past half the free disk | 2026-08-16 |
| Is a swirl diffuser better than directed vanes? | **Better at MIXING, which is not the objective.** Mixing caps ε_a at 50 %, piston reaches 100 %, the chamber is at 10 % — and `U_bulk` = 0.262 m/s means plug flow puts nearly the whole tray in the 0.3-0.8 m/s band. But it exposed a real gap: the cascade turns the jet without FILLING the cross-section (Ø 40 is 10 % of free area). **Radial spread is kept, swirl is bracketed.** `S > 0.6` gives vortex breakdown = a standing central recirculation = re-breathing, and the chamber is 4.7 port diameters against the 10-20 swirl needs to decay. Screen is now control / cascade-30 / radial-15 (`S` 0.19) / radial-40 (`S` 0.60). See `doc/diffuser/design.md` §3a | 2026-08-16 |
| **Fan / port / diffuser** | **CHANGED 2026-08-16: Sunon MF50100V2, Ø 40 mm ports, 5-vane inlet diffuser.** `Q` 1.25 → **11.77 m³/h (solved, not chosen)**, `Re_port` 1458 → **6863 (turbulent)**, `τ` 6.71 → 0.71 s. See the box in §6.2 and `doc/diffuser/design.md` | 2026-08-16 |
| Is the transient still "flat in `Q`"? | **No — that identity assumed a FIXED PORT.** Steps ∝ `U`/`Q` ∝ 1/`A`, so quadrupling the port area makes it **~4× cheaper: ~5 h/case, not ~20 h**. This is what makes a 4-case diffuser screen affordable | 2026-08-16 |
| Is the model spread still the largest error bar? | **Not at this operating point.** `Re_port` = 6863 is turbulent, so `kOmegaSST` is defensible on its own terms; the 76 % spread existed because `Re_port` = 1458 was below any closure's validity | 2026-08-16 |
| Can the chamber be over-ventilated? | **No.** `U_bulk` = 0.8 m/s needs 35.9 m³/h, unreachable with this fan at any port size. The only route to exceeding the ceiling is a surviving jet core; the only route to 0.3 m/s everywhere is piston flow. **The diffuser brief is jet → plug** | 2026-08-16 |
| ⚠ Why is `diffuser.eMesh` missing from snappy `features`? | **Same reason as `tray.eMesh`, and it is deliberate.** The shroud rim, vane leading edge and vane ends are all embedded in solid so their junctions are transversal, which means every vane root edge lies inside material. Feature snapping onto buried edges grows a skirt that `Mesh OK` cannot see. Level-4 `refinementSurfaces` resolves the 1.5 mm vanes without it | 2026-08-16 |
| Does `foamDictionary -set` preserve a dict's comments? | **NO — it rewrites the whole file from the parsed dictionary and DISCARDS EVERY COMMENT.** Measured: `snappyHexMeshDict` went 300 → 255 lines and lost all its documentation, including an anchor a later `sed` depended on. Use a targeted in-place edit for any dict whose comments are load-bearing | 2026-08-16 |
| **Tray geometry** | **CHANGED 2026-08-16 by design decision: flush with all four walls, filling the entire internal floor.** No side slots, no end gaps. `V_air` 2.530 → **2.3296 L**, τ at `Q` = 1.25 7.29 → **6.71 s**, tray metric area 0.014375 → **0.0224 m²**, m0 380 k → **261 k cells**. See the box in §6.1 | 2026-08-16 |
| Does the `floor` patch survive a flush tray? | **No — snappy drops it entirely.** Zero fluid faces, so it is absent from `constant/polyMesh/boundary`; the fluid domain now begins at the tray top, z = 25 mm. Harmless: the `0.orig` BCs are regexes (`"(floor\|walls\|hood\|tray)"`) and a non-matching alternative needs no edit. Verified by a solver smoke test — `yPlus` reports walls/hood/tray and does not error | 2026-08-16 |
| Can the tray carry surface layers now? | **Yes, and it does — 4, matching the walls.** `nSurfaceLayers 0` existed only because layers would not fit in a 6-cell slot. Measured at m0: **3.97 layers, 85.3 % coverage**, better than the walls' 70.1 %. **Tray wall shear is reportable on flush-tray cases** — and only those | 2026-08-16 |
| ⚠ Why is `tray.eMesh` missing from snappy `features`? | **Deliberate — putting it back corrupts the mesh.** The flush tray is written 1 mm oversize so its faces are not coplanar with the walls, which means every one of its edges is buried in solid. Explicit feature snapping then drags mesh points onto them, leaving a **skirt 1 mm past the chamber walls** (patch bboxes x = −0.001…0.121) and a **+0.49 mL** volume excess = perimeter × 1 mm × 0.8 mm. Removing it gives an exactly flat tray patch and −0.34 mL. Caught by the volume check, invisible to `Mesh OK` | 2026-08-16 |
| Is the flush-tray tray metric comparable to the old one? | **No.** `trayPlane` now averages over 0.0224 m² *including the near-wall boundary layers*; the old 0.014375 m² window sat entirely in the interior. Expect a lower mean speed from the window change alone. **Do not compare against the 0.02947 m/s Phase 1 headline like-for-like** | 2026-08-16 |
| Why is a DIFFUSED case 4× slower than the control? | **Genuine physics, not a stale constant.** Level-4 refinement puts 0.417 mm cells in the fastest flow, so `maxCo 6` binds instead of `maxDeltaT` and Δt falls 8.333e-4 → 2.034e-4. Verified on the `CourantNo` field: 100 % of Co > 3 cells lie within 12 mm of the inlet face, median edge 0.415 mm — **level-4 cells, not slivers.** The mesh's actual smallest cell (0.147 mm shroud sliver) is NOT the limiter | 2026-08-17 |
| Can `maxCo` be raised to recover it? | **No.** At `maxDeltaT` the diffused mesh reaches **max Co 25.1**, with 0.935 % of domain volume above Co 4 where the accepted control has **exactly 0 %**. The tail, not the mean, is the constraint — casc30's volume-weighted mean Co is 0.114 vs the control's 0.230, i.e. it is *more* time-resolved on average | 2026-08-17 |
| Can refinement be cut to recover it? | **Not without damaging the study.** Shroud-only level 4 → 3 gives **1.06×** (72 % of high-Co cells are in the vane passage, not at the shroud); whole-diffuser 4 → 3 gives exactly **2.00×** but puts a 1.5 mm vane on 1.8 cells — the §7 tray-slot pathology applied to the feature being screened | 2026-08-17 |
| Do the three diffuser concepts cost the same? | **No — radial is ~1.6× the cascade.** 12 vanes + a Ø 12 mm hub block far more bore than 5 plates, so the passage runs faster and Δt falls: casc30 2.034e-4 (23,697 steps, 12.6 h) vs rad15 1.260e-4 (38,245 steps, ~20.4 h). **The screen is ~53 h, not ~20 h** | 2026-08-17 |
| Does pairing two cases across the CCDs help? | **No — measured 0.517 steps/s paired vs 0.521 solo, a net loss**, while slowing the incumbent 1.60×. CCD1 is **1.70× slower per step** than CCD0 on identical work. Run sequentially on CCD0. See §3.2 | 2026-08-17 |
| ⚠ Does `Allrun` resume an interrupted run? | **No — and worse, it silently skips.** `runPinned` carries the same `[ -f log.$app ] && return 0` guard as `runApplication`, so re-running `Allrun` on an interrupted case **skips the solve entirely** and reconstructs whatever partial state exists as though finished. To resume: move `log.<solver>` aside (leave `log.decomposePar.fields` in place so `processor*/` survives) and re-run — `startFrom latestTime` does the rest, bit-exactly, since `writeFormat binary` stores raw doubles | 2026-08-17 |
| ⚠ Does a SIGSTOP'd run survive its session? | **No.** A suspended job gets SIGHUP+SIGCONT when the owning session exits and dies — observed as `mpirun: Forwarding signal 18 to job` as the last log line. Launch long runs with `setsid nohup … &` so they are reparented to init and immune | 2026-08-17 |

### 10.4 Needed later, not blocking anything now

> ### ⚠ 2026-08-15 — Phase 3 is a 4–6 DAY compute job, not an afternoon. Scope it deliberately.
>
> Both sweep drivers were written before the flow was known to be unsteady, and both would have
> produced nothing usable: `sweep_gravity.sh` ran **steady `buoyantSimpleFoam` on `m2`** with
> the default `kOmegaSST`, and `sweep_Q.sh` ran **steady on `m2`** while describing itself as
> "three cheap runs". Every case would have failed to converge, at ~5 h each, and the plots
> would have looked fine. Both are rewritten to `m0 --jetRefine --transient` with the model
> picked from `Re_port`.
>
> The honest cost, at the measured 24,546 steps/case:
>
> | | per case | whole sweep |
> |---|---|---|
> | `sweep_Q.sh` — 3 rungs, isothermal | **~17 h** (measured, 2.53 s/step) | **~52 h** |
> | `sweep_gravity.sh` — 4 `g` + 0 g cross-check, buoyant | **~50 h** (estimated) | **~250 h ≈ 10 days** |
>
> **The buoyant figure went UP after measurement, not down.** The Phase 2 smoke test
> (`runs/p2_smoke_m0`) ran `buoyantPimpleFoam` at **20.3 s/step** on 4 ranks under heavy
> contention, against 7.0 s/step for `pimpleFoam` on the same mesh and rank count — i.e.
> **buoyant is ≈ 2.9× the isothermal cost per step**, from the extra energy equation and a
> stiffer pressure problem. Scaling the clean 8-rank isothermal rate of 2.53 s/step by that
> factor gives ≈ 7.3 s/step ⇒ **~50 h per case**.
>
> ⚠ That is an extrapolation across two different contention levels, so treat it as an order of
> magnitude, not a number. **Take one clean 8-rank measurement before committing to Phase 3** —
> a few hundred steps is enough, and the difference between 30 h and 50 h per case decides
> whether the sweep is a long weekend or a fortnight.
>
> **Recommendation: run the two `g` ENDPOINTS first** (`GVALS="0 9.81"`). If 0 g and 1 g are
> indistinguishable within their correlated-sample error bars, there is no `Ri` crossover to
> resolve and the intermediate Lunar/Mars points are not worth the machine time. Both scripts
> take `GVALS`/`QVALS` and `MESH` from the environment for exactly this.

7. **Gravity regimes of interest** — which values beyond 1 g, and what is the physical context
   (spaceflight, lunar/Mars surface, centrifuge)? Drives whether `g = 0` exactly is needed.
   Phase 3 only. **Now also a budget question** — see the cost box above.
8. **What decides "good"?** Uniformity of velocity over the tray? A minimum air speed at
   canopy level? ACH? Temperature spread? The objective function should be defined before
   optimising anything. **Now answerable in concrete terms** — the metric surface is the
   **0.0224 m²** tray top at Z = 2.5 cm (the full internal floor since the tray went flush,
   2026-08-16; it was 0.014375 m²).
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
