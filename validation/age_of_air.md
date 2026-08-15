# Mean age of air — machinery, verification, and a first number

Investigated 2026-08-15. Mean age of air is the ventilation-effectiveness metric this project
cares most about (CLAUDE.md §8.4), and until now nothing had checked that the number it
produces is right. Three things came out of looking: **the documented recipe did not work at
all**, **the solve looked badly unconverged but is not**, and there is **an exact identity that
settles the question**, now wired into the templates.

---

## 1. The documented recipe cannot work — use `scripts/age_of_air.sh`

CLAUDE.md §8.4 said:

```bash
cp <T>/phiMean <T>/phi
postProcess -func age -time <T>
```

Both halves fail:

1. **`-func age` finds no config.** There is no `age` file under `etc/caseDicts/postProcessing/`
   in this build, so the utility emits `Cannot find functionObject file age` as a *warning* and
   **exits 0 having computed nothing.** Silent, and it looks like success.

2. **`age` cannot run under `postProcess` at all.** From
   `src/functionObjects/field/age/age.C`, inside `read()`:

   ```cpp
   const auto& phi = mesh_.lookupObject<surfaceScalarField>(phiName_);   // line 128
   ```

   `phi` must be **registered when the function object is constructed**. `postProcess` builds
   its function objects *before* reading fields, and never auto-loads a `surfaceScalarField`:

   ```
   failed lookup of phi (objectRegistry region0)
   available objects of type surfaceScalarField: 0()
   ```

   `-fields '(phi U)'` does not help — that loads at execute time, strictly after construction.
   `simpleFoam -postProcess` does not help either, same ordering.

**`age` must run inside a solver**, where `createFields` has registered `phi` and the turbulence
model — which is why the in-solver `ageMean` series in every steady run works fine.
`scripts/age_of_air.sh` does that: it copies the case to `<case>/ageEval/`, puts `phiMean` in as
`phi`, and runs the solver for **one** deliberately tiny step (1e-8 s; 1 iteration for a steady
solver) purely to give the function object a live registry. Verified to reproduce the in-solver
value exactly — 35.7106 s from the script against 35.7247 s in-solver at the same time.

> **Trap, hit and guarded against.** `endTime` must be *representably* larger than `startTime`.
> At t = 4000 an increment of 1e-8 printed with `%.10g` comes back as `4000`; `endTime` then
> equals `startTime`, the solver prints `Starting time loop` → `End` having computed nothing,
> and exits 0. The script formats with `%.16g` and asserts the loop turned over.

---

## 2. The verification: `<age>_outlet == tau`, exactly

Sandberg's ventilation theory gives one exact identity. Integrating the age equation
`div(phi, age) = 1` over the domain, with `age = 0` at the inlet and no flux through walls:

```
    <age>_exhaust  ==  tau  =  V_air / Q
```

for **any** steady flow, whatever the internal recirculation looks like. It is mass
conservation applied to the age field, not a modelling result, so it holds for a
short-circuiting chamber exactly as for a well-mixed one. That makes it a free, sharp check on
whether the age transport equation actually converged — and it is now a function object,
`ageOutlet`, in `templates/system/functions/age`.

It has to be the **flux-weighted** average (`weightedAreaAverage` + `weightField phi`). A plain
`areaAverage` is a different quantity and will not equal τ.

**Do not report an age number without reading `ageOutlet` first.**

## 3. The solve looks unconverged. It is not.

Every run in `runs/` shows this, and it is alarming:

```
DILUPBiCGStab: Solving for age, Initial residual = 1, Final residual = 145.05, No Iterations 1000
DILUPBiCGStab: Solving for age, Initial residual = 0.224,  Final residual = 1.9e-05, No Iterations 1000
```

The first solve *diverges*, later ones hit the 1000-iteration cap, and the outer `nCorr` loop's
initial residual sits at 0.22–0.30 and never contracts. The reason it never contracts is that
`div(phi,age)` uses `bounded Gauss limitedLinear 1`, whose limiter is solution-dependent: the
matrix changes every outer iteration, so a converged *linear* solve does not give a small
*next* initial residual. There is also no `age` entry in `relaxationFactors/equations`, so the
function object's `ageEqn.relax(relaxCoeff)` is a no-op (`relaxCoeff` = 0).

**But the identity says the answer is fine.** Measured on `p1_q1p25_m0` (m0, laminar,
Q = 1.25 m³/h, τ = 7.2866 s):

| `div(phi,age)` | ageMean [s] | ageMax [s] | **ageOutlet [s]** | **identity error** | ε_a |
|---|---|---|---|---|---|
| `limitedLinear` (template) | 35.711 | 78.331 | **7.27878** | **−0.108 %** | 10.2 % |
| `upwind` | 32.462 | 73.136 | **7.28547** | **−0.016 %** | 11.2 % |

Both conserve to ~0.1 % or better. The residual noise is **cosmetic**, not a correctness
problem, and this table is the evidence for saying so.

### Keep `limitedLinear`

`upwind` converges far more cleanly — its first solve goes 1 → 5.3e-7 in 347 iterations where
`limitedLinear` diverges — and its identity error is 6.6× smaller. It is still the **wrong
choice**, because it buys that by smearing the age field: it reports a mean age **9.1 % lower**,
i.e. it makes the chamber look better ventilated than it is. That is the same trade CLAUDE.md
§7 refuses for the momentum equation, for the same reason.

**Carry 9 % as the discretisation uncertainty on any reported age.** It is far larger than the
0.1 % conservation error, so the scheme, not the linear solver, is the limiting error here.

---

## 4. First number: the chamber short-circuits badly

On the `p1_q1p25_m0` field, τ = 7.2866 s:

| | value | in units of τ |
|---|---|---|
| volume-mean age | **35.7 s** | **4.90 τ** |
| max local age | **78.3 s** | 10.75 τ |
| outlet age *(check)* | 7.279 s | 0.999 τ ✓ |
| **air exchange efficiency ε_a = τ/(2⟨age⟩)** | **10.2 %** | — |

For reference ε_a is **50 %** for perfect mixing and **100 %** for piston flow. **10 %** means
severe short-circuiting: the jet runs inlet → outlet and most of the chamber volume is barely
participating.

### Where the dead volume is — and it is not where §6.1 predicted

`ageHood` and `ageCanopy` were added to the template to locate it. Same field, same run:

| zone | age [s] | × τ | |
|---|---|---|---|
| `ageCanopy` — growing volume, tray top → 50 mm | 34.016 | **4.67** | *best of the three* |
| `ageHood` — z > 96.7 mm, 0.72 L, entirely above the jet | 35.147 | **4.82** | |
| `ageMean` — whole chamber | 35.711 | **4.90** | |
| `ageMax` — worst single cell | 78.331 | 10.75 | |
| `ageOutlet` — **identity check** | 7.279 | **0.9989** ✓ | |

**The hood is not a distinct dead zone.** It sits at 0.984 of the chamber mean — statistically
indistinguishable from everywhere else, and the canopy zone is marginally *better* than average.

CLAUDE.md §6.1 predicts the opposite in strong terms: *"Expect it to be the worst-ventilated
region by a wide margin; the `age` function object will show this immediately."* On this
evidence **it does not.** The correct picture is worse and simpler than the predicted one: the
chamber is not a well-mixed core plus a stagnant cap, it is **uniformly stale at ~4.7–4.9 τ
throughout**, because the jet short-circuits to the outlet and ventilates *nothing* properly.
A localised dead zone can be fixed by aiming the jet; uniform staleness at ε_a = 10 % is a
statement about the inlet/outlet arrangement itself.

Note the 10.75 τ maximum lives somewhere outside both named zones — corners, or behind the
tray. Worth locating in ParaView on the `age` field before drawing design conclusions.

> **Do not over-read this yet.** It is one non-converged steady field (see the box below), and
> the hood-vs-chamber gap (0.984) is far smaller than the 9 % scheme uncertainty in §3. The
> claim that survives is the *ordering* — no zone is dramatically worse than the mean — not the
> individual figures. Re-check on `phiMean` from the transient before amending §6.1.

### The other age number in the repo disagrees by 2.8× — and it is confounded

`p1_baseline_m1` (the Q = 5 m³/h, m1, kOmegaSST steady run) has its own in-solver age series:

| case | `Q` | model | mesh | age/τ | ε_a |
|---|---|---|---|---|---|
| `p1_baseline_m1` | 5 | kOmegaSST | m1 | **1.73** | **28.9 %** |
| `p1_q1p25_m0` | 1.25 | laminar | m0 | **4.90** | **10.2 %** |

**Do not read that as "higher flow ventilates better."** All three of `Q`, turbulence model and
mesh differ between the two rows, and one of them is known to bias this metric hard: kOmegaSST
was measured at `ν_t/ν` ≈ 5–6 at this scale (CLAUDE.md §5.2), and spurious eddy viscosity
*mixes*, which lowers apparent age. An over-diffusive model will always report a better-
ventilated chamber than it is.

The transient matrix disentangles this cleanly, because `m0_lam_jet` and `m0_kom_jet` differ in
**nothing but the turbulence model** — same mesh, same `Q`, same BCs. Running `age_of_air.sh` on
both `phiMean` fields gives the model spread on the ventilation metric directly, alongside the
existing 89 % spread on tray mean speed. That is the number to quote, not either row above.

### First transient evaluation — the pipeline works, and the numbers corroborate

Run on `phiMean` from `p1_trans_q1p25_m0_lam_jet` at t = 20.5 s (2.81 τ), i.e. the first
averaged write the run produced:

| metric | steady field | × τ | `phiMean` | × τ | change |
|---|---|---|---|---|---|
| `ageMean` | 35.711 | 4.90 | **36.145** | **4.96** | +1.2 % |
| `ageMax` | 78.331 | 10.75 | 82.184 | 11.28 | +4.9 % |
| **`ageOutlet`** | 7.279 | 1.00 | **7.283** | **1.00** | +0.1 % |
| `ageHood` | 35.147 | 4.82 | 35.024 | 4.81 | −0.3 % |
| `ageCanopy` | 34.016 | 4.67 | 34.426 | 4.72 | +1.2 % |

**The identity holds to −0.045 %** — tighter than the steady case's −0.107 %. ε_a comes out
**10.1 %** against 10.2 %, and the hood sits at **0.969** of the chamber mean against 0.984.
Both headline conclusions survive re-evaluation on a genuinely time-averaged flux: the chamber
short-circuits by roughly an order of magnitude, and the hood is not a distinct dead zone.

This also closes the last untested link in the analysis chain — `age_of_air.sh` had only ever
been exercised on a *steady* case, and the transient path (`pimpleFoam`, `deltaT` 1e-8) is
exactly where the `%.16g` zero-iteration trap lives. It ran clean.

> **⚠ Do not read the agreement as confirmation of convergence.** At t = 20.5 s, `fieldAverage`
> has been running since `timeStart` = 20.05 s — so `phiMean` is an average over **0.45 s
> = 0.06 τ**. That is still effectively a snapshot. The close agreement with the steady field
> says the two snapshots resemble each other, not that either is the converged mean. Re-run at
> the end of the solve, when `phiMean` covers the full 28.1 s window.

> ### ⚠ This number is provisional and will be superseded
>
> It is computed on the field of a **steady run that never converged**, because the flow at this
> `Q` is genuinely unsteady (CLAUDE.md §5.1, §7) — so it is one arbitrary snapshot of a flapping
> jet, not a mean flow. The proper number comes from `phiMean` of the transient matrix
> (`validation/transient_matrix.md`), which is what `scripts/age_of_air.sh` is built for.
>
> Take from this section that the machinery works and is verified, and that the chamber
> short-circuits by roughly an order of magnitude — not the third significant figure.
