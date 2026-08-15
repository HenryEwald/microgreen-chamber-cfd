# Phase 1 transient matrix — Q = 1.25 m³/h

**Status: running, started 2026-08-15.** Numbers land here as the arms finish.

---

## Summary — what is known so far

Ordered by how much it should change what you do. Everything below is expanded and sourced
later in this document; nothing here is a claim without a measurement behind it.

**Established**

| finding | evidence | where |
|---|---|---|
| The unsteadiness is **chamber-scale, not a jet-column instability**. `St ≈ 0.3` is the wrong model | 0.0–0.2 % of power in the 5–30 Hz band, Nyquist 255 Hz so the band *is* resolved | §4 |
| The dominant motion is a **chamber-scale recirculation, period ≈ 10.8 s ≈ 1.5 τ** — so the averaging window holds only **≈ 2.6 cycles** | resolved at a 21.5 s record (peak cleared the window fundamental); order-of-magnitude, pinned to ~1 frequency bin | §4 |
| The **model spread on tray mean speed is ~110 %** | +117 % and +107 % at two independent matched-time windows | §4a |
| ⚠ **Any statistic on a window shorter than the ≈ 10.8 s period reports the window, not the flow** | probe correlation `r` swings +0.99 → −0.99 → −0.13 across successive 2 s windows (≈ 0.2 of a cycle) | §4a |
| `buoyantPimpleFoam` **was broken** (`rhoFinal` missing); both buoyant solvers now verified | died on time step 1; fixed as `"rho.*"`, smoke tests pass | §4b |
| Phase 3 costs **~50 h/case ⇒ ~250 h** for the full 4-`g` sweep | buoyant measured at 2.9× the isothermal per-step cost | §4b |

**Provisional — do not quote without the caveat**

| finding | why provisional |
|---|---|
| Mean age **4.96 τ**, ε_a ≈ **10 %**, hood at **0.97** of the chamber mean — i.e. uniformly stale, **not** the hood-as-dead-zone that §6.1 predicts | `phiMean` had averaged only 0.06 τ at the time of writing | `age_of_air.md` |

**Retracted during the session — recorded so they are not re-derived**

| withdrawn claim | how it failed |
|---|---|
| "`kOmegaSST` **suppresses** the instability outright" (from `r` = −0.36 laminar vs +0.999 RANS at 1.04–1.31 τ) | the matched repeat at 1.92–2.19 τ **reversed** it: +0.581 laminar vs −0.997 RANS. Both arms show both states — `r` on a 2 s window tracks oscillation *phase*, not state. §4a |
| "Flapping **onsets at ≈ 1.05 τ**" | same metric, same flaw; and the four windows shared an endpoint so were not independent. §4 |

Both were flagged provisional when written and both were killed by the test that was named at
the time. The general lesson is now the fourth row of the Established table — and it was the
*agreement with an existing prior* (CLAUDE.md §5.2's over-diffusion argument) that made the
first one feel solid enough to write down.

**Scope consequences you should decide on**

- **This run answers the model-spread question (~110 %) and cannot answer the mesh question
  (0.3 %)** — at ≈ 2.6 independent cycles, mesh-level differences are below the noise floor of
  any record of affordable length. Reporting them as resolved would be wrong. See §4.
- **Phase 3 at ~250 h is probably not worth committing blind.** Run the two `g` endpoints first
  (`GVALS="0 9.81"`, ~100 h); if 0 g and 1 g do not separate beyond their error bars there is no
  `Ri` crossover and the intermediate points buy nothing. See §4b.

---

Everything in Phase 1 up to now has been a *steady* run that did not converge, because the
chamber flaps at both ends of the flow ladder (CLAUDE.md §5.1, §7). Four steady runs were
spent establishing that. This is the first time-accurate answer.

---

## 1. What this matrix is for

A transient answer is a **time average plus a fluctuation level**, so the questions are not
"what is the tray speed" but "what is it, ± what, and which of our modelling choices moves it
by more than that". Three comparisons, each isolating one variable:

| Comparison | Arms | Question |
|---|---|---|
| **Numerical damping** | `m0` plain vs `m0 --jetRefine` | Does an unresolved shear layer suppress the fluctuation? |
| **Model spread** | `m0 --jetRefine` laminar vs kOmegaSST | Is CLAUDE.md's 89 % model spread real on a *time average*? |
| Mesh independence | `m0 --jetRefine` vs `m1 --jetRefine` | **Not run — ~68 h, see §5** |

Every arm is at `Q` = 1.25 m³/h (`Re_port` = 1458, the laminar band), `g` = 9.81, isothermal,
6.6 τ with the first 2.75 τ discarded. τ = 7.29 s, so endTime 48.11 s, averaging from 20.05 s.

## 2. The arms

| Case | Mesh | `h_port` | Model | cells | Δt | steps | ranks / cores | measured |
|---|---|---|---|---|---|---|---|---|
| `p1_trans_q1p25_m0_lam_jet` | m0 +jet | 0.833 mm | laminar | 415,334 | 1.96e-3 | 24,546 | 8 / `0-7` (CCD0) | **2.53 s/step ⇒ ~17 h** |
| `p1_trans_q1p25_m0_kom_jet` | m0 +jet | 0.833 mm | kOmegaSST | 415,334 | 1.96e-3 | 24,546 | 8 / `8-15` (CCD1) | **3.68 s/step ⇒ ~25 h** |
| `p1_trans_q1p25_m0_lam` | m0 | 1.667 mm | laminar | 379,918 | 3.92e-3 | 12,270 | 4 / `0-3`, **queued** | starts when arm 1 ends |

Rates are the steady-state instantaneous figures (last 20 steps), not the cumulative average —
the latter is inflated by the `deltaT` ramp from `1e-5` and is ~15 % pessimistic.

`p1_trans_q1p25_m0_lam_jet` is **the primary result** — the physically defensible model
(laminar at `Re_port` = 1458) on the mesh that resolves the shear layer over 73 % of the path.
The kOmegaSST arm is slower per step both because it carries two extra transport equations and
because CCD1 has 32 MB of L3 against CCD0's 96 MB of V-cache.

The two jet arms run concurrently across all 16 physical cores via the `FOAM_CPUSET` override
added to `templates/Allrun`; the third is queued rather than run alongside, because 3 × 8 ranks
does not fit.

> ### ⚠ The `FOAM_CPUSET` override needed a guard — and this is why
>
> First launch put all three arms on 4 cores each (`0-3`, `4-7`, `8-11`). But the 50 k-cells/rank
> floor in `Allrun` sizes the *rank count* independently, and at 415,334 cells it chose **8
> ranks** — so `FOAM_CPUSET=0-3` packed **8 MPI ranks onto 4 physical cores**. mpirun said
> nothing; the log cheerfully printed `8 ranks, pinned to cores 0-3`.
>
> Cost: **7.0 s/step against 2.94 s/step properly placed — a 2.4× loss**, and it is precisely
> the SMT oversubscription CLAUDE.md §3.2 forbids, arrived at by accident. `runPinned` now
> measures the cpu-set width and refuses to launch when it is narrower than the rank count.
> Documenting the constraint in a comment was not enough — I then violated my own comment.

## 2b. Mean age of air

Not a function object during the run — `age` solves a *steady* transport equation, so firing it
at write time on a flapping jet answers a question nobody asked (CLAUDE.md §8.4). It is
evaluated once, post-hoc, on the time-averaged flux `phiMean`:

```bash
scripts/age_of_air.sh runs/p1_trans_q1p25_m0_lam_jet
```

That recipe turned out to be broken as documented, and the investigation found the chamber
short-circuits badly (ε_a ≈ 10 % against 50 % for perfect mixing). Full write-up:
`validation/age_of_air.md`. The templates now also report `ageHood` and `ageCanopy`, so the
transient will say **where** the dead volume is, and `ageOutlet`, which must equal τ and is the
check that the age solve converged at all.

## 3. Two bugs found while setting this up

Both are recorded in CLAUDE.md §5.1 / §10.3; the short version:

1. **`maxDeltaT` was a hard-coded `1e-3`**, sized for `Q` = 5 m³/h. At `Q` = 1.25 it bound at
   max Courant 2.03 against a `maxCo` of 6 — the clock cap, not the Courant condition. Δt
   stayed at the `Q` = 5 value while endTime grew 4× with τ, making the low-`Q` run **4× more
   expensive than the high-`Q` one**. Now set as `2.6·h_port/U_in`, a fixed jet Courant
   number, which reproduces the template's own measured 4.9e-4 anchor exactly.

2. **"Lower `Q` is cheaper" is arithmetically wrong** and has been retracted. τ ∝ 1/`Q` and
   Δt ∝ 1/`Q` cancel: a 6.6-τ transient is ~24.5 k steps at *every* flow rate. The old claim
   applied the Δt saving and forgot the endTime penalty.

Neither affects any previously reported result — no transient had ever been run — but the
second was being used as a reason to prefer `Q` = 1.25, and that reason is now withdrawn.
The free-air argument for 1.25 (CLAUDE.md §6.2) is untouched and still stands on its own.

## 4. How the numbers will be reported

```bash
python3 validation/compare_transients.py runs/p1_trans_q1p25_m0_*
python3 validation/compare_transients.py --window-sweep runs/p1_trans_q1p25_m0_lam_jet
python3 validation/plot_transient.py runs/p1_trans_q1p25_m0_lam_jet
```

**The error bar is not `sd/√N`.** Successive samples of a flapping jet are strongly
correlated — traySignal samples every time step, ~500 Hz, against a fluctuation whose integral
timescale is of order a second, so a thousand consecutive samples are worth roughly one
independent look at the flow. The standard error used is

```
    SE = sd / √N_eff ,    N_eff = N·Δt / (2·T_int)
```

with `T_int` the integral timescale from the autocorrelation, truncated at its first zero
crossing. `validation/test_stats.py` verifies this against signals with known answers, and
measures what the naive estimator would cost:

| estimator | coverage of the true mean by ±2 SE (target ~95 %) |
|---|---|
| `sd/√N_eff` (used) | **93 %** |
| `sd/√N` (not used) | **15 %** |

A mesh or model difference is reported as real only when it exceeds the combined SE of the two
arms. This is the rigorous version of the comparison CLAUDE.md §9.6 flagged as *"not a GCI —
strong indicator, not proof"*.

### Contingency: if `N_eff` comes out too small, extend the run — do not shrink the error bar

The averaging window is 3.85 τ = 28 s. Whether that is *enough* depends on the integral
timescale of the flapping, which is not known in advance — that is the whole reason `N_eff` is
reported rather than assumed. Rough guide from the table `compare_transients.py` prints:

| `N_eff` | verdict |
|---|---|
| ≳ 30 | fine — SE ≈ sd/5.5, comfortably tighter than the mesh/model differences being tested |
| 10–30 | marginal — report the SE prominently and do not claim small differences |
| < 10 | **not enough** — the mean is not resolved; extend the run |

> ### ⚠ Adequacy is relative to the effect size. Read this before extending anything.
>
> The table above is a rule of thumb, and taken literally it would say this study needs a much
> longer run. The spectrum measurement (below) bounds the dominant timescale at **≥ 5.4 s and
> still rising with the record**, so the 28.1 s averaging window holds only **~5 independent
> cycles**. By the table, "not enough."
>
> But `N_eff` is only meaningful against the difference being tested:
>
> | question | effect size | verdict at `N_eff` ≈ 5 |
> |---|---|---|
> | **model spread** (laminar vs kOmegaSST) | **~89 %** on tray mean speed | **answerable, comfortably** — SE ≈ sd/2.2, so even a 10 % RMS gives ~4.5 % SE against an 89 % effect |
> | mesh (m0 vs m1) | ~0.3 % | **not answerable** — swamped many times over |
> | tray uniformity CoV | ~2 % mesh, ±8 % temporal | not answerable |
>
> **So the run as configured answers the question it was built to answer** — item 3 of
> CLAUDE.md §10.2, the largest error bar in the project — and does not answer the finer ones.
> That is the honest scope, and doubling the wall clock to ~44 h would not change it much: even
> 10 τ only reaches ~10 cycles, still far short of resolving a 0.3 % mesh effect.
>
> **Decision: do not extend.** Report the model spread with its error bar, and state explicitly
> that mesh-level differences are below the noise floor of this record rather than quietly
> reporting them as if they were resolved.

> ### Forecasting `N_eff` mid-run — measured 2026-08-15 at t = 9.44 s (1.29 τ)
>
> Sampling `m0_lam_jet` over progressively later windows, to see whether the statistics have
> settled enough to forecast the final `N_eff`:
>
> | window [s] | n | mean [m/s] | RMS % | `T_int` [s] |
> |---|---|---|---|---|
> | 1.89 – 9.44 | 3850 | 0.02354 | **18.6** | **1.023** |
> | 3.30 – 9.44 | 3128 | 0.02540 | 8.0 | 0.600 |
> | 4.72 – 9.44 | 2407 | 0.02633 | 2.3 | 0.542 |
> | 6.13 – 9.44 | 1685 | 0.02626 | 2.5 | 0.537 |
> | 7.55 – 9.44 | 963 | 0.02586 | **2.4** | **0.333** |
>
> Both `T_int` and RMS fall steeply as the window moves later. **That is the start-from-rest
> transient decaying, not a property of the flow** — a monotonic spin-up from zero looks like a
> long correlation time to an autocorrelation estimator. The mean is meanwhile settling
> (0.0235 → 0.0259).
>
> Projecting the 28 s averaging window:
>
> | if `T_int` settles at | `N_eff` at 6.6 τ | at 10 τ |
> |---|---|---|
> | 0.3 s | 47 ✓ | 88 |
> | 0.6 s | **23** (marginal) | 44 |
> | 1.0 s | 14 (marginal) | 26 |
> | 1.5 s | 9 ✗ | 18 |
>
> **Decision: do NOT extend `endTime` pre-emptively.** At 1.29 τ the jet has crossed the chamber
> but the large-scale recirculation has not established, and the flapping CLAUDE.md §5.1
> documents (period ~1000–1400 SIMPLE iterations in the steady runs) has not onset — the
> present 2.4 % RMS is well below the ±6.5 % those runs showed. So these numbers are a lower
> bound on both `T_int` and RMS, and forecasting from them would be exactly the premature
> inference this whole document is about avoiding.
>
> Extending costs +50 % wall clock on both arms. Measure `N_eff` on the finished run, then
> extend if it lands under ~30 — the restart is cheap and loses nothing.
>
> #### ⚠ WITHDRAWN — "the flapping onset was caught live at ≈ 1.05 τ"
>
> This block previously reported the `jetProbes` correlation `r` over windows all ending at
> 1.30 τ — +0.989, +0.944, +0.912, then **−0.417** as the start slid later — and concluded the
> instability onsets at ≈ 1.05 τ.
>
> **Withdrawn.** The same metric, evaluated in successive 2 s windows later in the run, swings
> from +0.993 to −0.995 and back (see §4a). `r` on a window much shorter than the ≥ 8.9 s
> dominant timescale tracks the *phase* of a slow oscillation, not the presence or absence of
> one. The apparent "onset" is one sign change in a signal that changes sign repeatedly.
>
> The four windows above were also **not independent** — all shared the same endpoint at 1.30 τ,
> so they are four overlapping views of largely the same data, which is why they looked like a
> clean progression.
>
> What is still true, and did not depend on this metric: the field genuinely does develop from
> rest, and RMS measured over the earliest windows is a **lower bound** because the flow had not
> finished spinning up. The 2.75 τ discard remains a sensible rule of thumb; it is simply not
> *validated* by an onset measurement, because there is no trustworthy onset measurement.
>
> Two things this does still settle:
>
> 1. **`T_int` and RMS from early windows are lower bounds**, whatever the onset time was.
> 2. **The unsteadiness is real and reproduces in the transient**, independently of the steady
>    runs that first exposed it (CLAUDE.md §5.1, §7). That rests on the tray signal carrying
>    real RMS and on the probe pair changing sign repeatedly — *that* it varies is robust; the
>    claim that any particular window shows "flapping" or "not flapping" is not.
>
> #### It is NOT a jet-column instability — `St ≈ 0.3` is the wrong model for this flow
>
> `functions/transientMonitors` justifies its sampling rate against a jet-column mode:
> *"St ~ 0.3 on D = 20 mm at 4.42 m/s gives ~66 Hz"* — which scales to **16.6 Hz** at the
> working `Q` = 1.25 m³/h. Spectrum of the lateral flapping signal (the difference of the two
> off-axis probes) over the post-onset record:
>
> | band | | share of power |
> |---|---|---|
> | chamber-scale, 1–5 s periods | 0.2–1.0 Hz | **94.3 %** |
> | intermediate | 1–5 Hz | 5.5 % |
> | **`St ≈ 0.3` jet-column band** | 5–30 Hz | **0.2 %** |
> | high frequency | 30–255 Hz | 0.0 % |
>
> Nyquist is 255 Hz, so the 16.6 Hz band is *well* resolved — **its emptiness is a real result,
> not a sampling artefact.** The motion is a slow, chamber-filling recirculation wander, which
> is also what the steady runs showed (§5.1: periods of ~1000–1400 SIMPLE iterations, with `Uy`
> pinned by mass conservation while the cross-stream recirculation wanders).
>
> **What cannot yet be said: the period.** The apparent spectral peak sits at 0.280 Hz, which is
> *exactly* `1/T` for the 3.57 s post-onset record — i.e. it is the lowest frequency the window
> can resolve, not a measurement. All that follows is **the dominant timescale is ≥ 3.6 s**,
> around half a residence time or more.
>
> **This is the number that sets the required run length**, and it is bigger than anything
> assumed so far. Re-measured as the record grew (`compare_transients.py --spectrum`):
>
> | post-onset record | 1/T [Hz] | peak [Hz] | timescale | power < 1 Hz |
> |---|---|---|---|---|
> | 3.57 s | 0.280 | 0.280 = 1/T | ≥ 3.6 s (bound) | 94.3 % |
> | 5.37 s | 0.186 | 0.186 = 1/T | ≥ 5.4 s (bound) | 96.4 % |
> | 8.92 s | 0.112 | 0.112 = 1/T | ≥ 8.9 s (bound) | 99.9 % |
> | **21.49 s** | **0.047** | **0.093 = 2/T** | **≈ 10.8 s — RESOLVED** | **100.0 %** |
>
> For the first three records the peak sat exactly at the window fundamental, so the timescale
> was only bounded below by however much record existed. **At 21.5 s it finally cleared the
> fundamental** — sitting in the second bin — making that the first genuine measurement.
>
> #### The dominant period is ≈ 10.8 s ≈ 1.5 τ
>
> Two caveats that keep it honest:
>
> - **Order of magnitude only.** Frequency resolution is 0.047 Hz and the peak is at 0.093 Hz,
>   so the period is pinned to about one bin — roughly a factor of two either way.
> - **~2 cycles in the record.** That is the minimum for "resolved" and no more.
>
> What it settles qualitatively: the motion is a chamber-scale recirculation at ~1.5 residence
> times, and the jet-column band is now **0.0 %** against **100.0 %** below 1 Hz.
>
> **Consequence: the 28.1 s averaging window holds ≈ 2.6 cycles** — consistent with the ~3
> inferred earlier from the bound, so nothing in the adequacy argument changes. It is now
> measured rather than inferred.
>
> *(Finding this also exposed a bug in `compare_transients.py`: its cycle-count line divided the
> averaging window by the record length, which is the right proxy only while the peak is
> resolution-limited. Once resolved it must use the period — it reported ~1 cycle where the
> period gives ~2.6. Fixed the moment the peak resolved; the function now branches on it.)*
>
> #### What is robust, and what is not
>
> **Robust** — the jet-column band is *empty*. That band (5–30 Hz) is well inside Nyquist
> (255 Hz), so its 0.0–0.2 % share is a measurement, not a resolution artefact. The `St ≈ 0.3`
> model is wrong for this flow, full stop.
>
> **Not established** — whether a characteristic period exists at all. Fitting a power law over
> 0.15–5 Hz gives `p ~ f^-3.1`, which *looks* like red noise (no characteristic timescale, mean
> converging only as √T). **Do not quote that slope.** With the dominant timescale ≥ 8.9 s and a
> record of 8.92 s there is **less than one full cycle** in the sample; an FFT of under one cycle
> is fitting a trend, and any trend produces a steep slope. A slow oscillation not yet resolved
> and genuine red noise are indistinguishable from this record.
>
> **Re-measure on the finished run**, where the averaging window is 28.1 s — 3× longer, and the
> first record able to say anything about whether a period exists.
>
> The practical consequence is unchanged and firm either way: **the averaging window holds only
> ~3 independent samples of the dominant motion.** See the adequacy note above for why that
> still answers the model-spread question and does not answer the mesh one.

Extending is cheap and safe, because `controlDict` has `startFrom latestTime` and `fieldAverage`
continues accumulating across a restart (it stores its state in `<time>/uniform/`):

```bash
cd runs/<case>
foamDictionary -entry endTime -set 96.2 system/controlDict   # e.g. 13.2 tau
rm log.pimpleFoam                                            # or Allrun skips the solve
FOAM_CPUSET=0-7 ./Allrun
```

Note `purgeWrite 5` keeps only the last five write times, which is fine — the statistics come
from `traySignal`/`jetProbes` (written every step, never purged) and from the running
`fieldAverage`, not from the stored time directories.

**Do not respond to a small `N_eff` by switching to `sd/√N`.** That is precisely the estimator
`test_stats.py` shows is wrong 85 % of the time, and it would turn "we cannot tell yet" into a
confident wrong answer.

## 4a. ⚠ RETRACTED — "kOmegaSST suppresses the instability" does not survive its own test

**This section previously claimed**, from a matched-time window at 1.04–1.31 τ, that the laminar
jet was flapping (`r` = −0.362) while the RANS jet was perfectly symmetric (`r` = +0.999), and
concluded that `kOmegaSST` *removes* the instability rather than merely over-diffusing it. It
was flagged provisional, with "repeat at a later matched time" as the stated test.

**The repeat reversed it.** Same metric, same method, matched window at 1.92–2.19 τ:

| window | laminar `r` | kOmegaSST `r` |
|---|---|---|
| 1.04–1.31 τ | **−0.362** (reads as flapping) | **+0.999** (reads as symmetric) |
| 1.92–2.19 τ | **+0.581** (reads as symmetric) | **−0.997** (reads as flapping) |

Both arms show both states. So the conclusion is withdrawn — and the reason matters more than
the conclusion did.

### The metric was measuring the window, not the flow

`r` in successive 2 s windows, laminar arm:

| window [s] | 8–10 | 10–12 | 12–14 | 14–16 | 16–18 | 18–20 | 20–22 | 22–24 |
|---|---|---|---|---|---|---|---|---|
| `r` | +0.247 | +0.880 | +0.993 | +0.636 | +0.886 | **−0.995** | −0.535 | −0.132 |

It swings through the entire range. **The dominant timescale is ≥ 8.9 s and these windows are
2 s — about 0.2 of a cycle.** Over a fraction of a cycle two off-axis probes can correlate
either way depending purely on where in the cycle you sample. `r` tracks the instantaneous
*phase* of a slow oscillation; it is not an indicator of whether an instability is present.

This is the same error as the spectral peak sitting at `1/T` (§4): **a statistic computed on a
window shorter than the phenomenon's own timescale reports the window, not the physics.** It
was made twice in one session, in different disguises, and the second time it produced a
plausible result that agreed with the prior in CLAUDE.md §5.2 — which is precisely why it got
written down as a finding before being tested.

### What survives

| claim | status |
|---|---|
| Tray mean spread laminar → kOmegaSST: **+117 %** (1.04–1.31 τ) and **+107 %** (1.92–2.19 τ) | **robust** — consistent across independent matched windows, and a mean is far less window-sensitive than a correlation |
| The flow is unsteady | **robust** — four steady runs never converged; the tray signal carries real RMS |
| `ν_t`/`ν` ≈ 5–6 for the RANS arm, `Re_eff` = 242 | **robust** — CLAUDE.md §5.2, a volume average, not a windowed statistic |
| kOmegaSST *suppresses* rather than *over-diffuses* the instability | **not established** — needs a metric evaluated over many cycles, i.e. the full 28.1 s window at minimum, and even that is only ~3 cycles |
| "Flapping onsets at ≈ 1.05 τ" (previously below) | **withdrawn** — rested on the same 2 s-window correlation. See §4 |

**Do not use `r` over a short window as a state indicator.** The `anti` column in
`compare_transients.py` now carries this caveat.

## 4a-bis. The kOmegaSST arm emits ~11,000 `bounding k` messages. It is benign — here is the check.

Anyone watching that log will see this and reasonably worry, because `bounding k` is exactly the
precursor `templates/transient/system/fvSolution` documents before a divergence: *"k and omega
reached 1e105/1e55 after 3295 `bounding k` messages"* in the `nOuterCorrectors 2` failure.

This is **not** that. Only `k` is bounded (never `omega`), and it is flat, not growing:

| fifth of run | max(k) | avg(k) |
|---|---|---|
| 1 | 0.0556 | 0.00281 |
| 2 | 0.0539 | 0.00268 |
| 3 | 0.0534 | 0.00270 |
| 4 | 0.0540 | 0.00269 |
| 5 | 0.0545 | 0.00268 |

Two things distinguish it from the documented divergence:

1. **No growth.** `max(k)` sits at ~0.054 for the whole run against the failure case's 1e105.
2. **The clipped value is positive.** Early messages had genuinely negative `k`
   (min = −8.2e-4) — that is the start-from-rest transient. Every recent one reads
   `min: 3.0e-16`, i.e. `k` is *positive but below OpenFOAM's `kMin` floor*. The solver is
   raising a near-zero value to the floor in cells where turbulence has decayed to nothing.

That decay is physically expected: `Re_port` = 1458 is in the laminar band, so over most of the
chamber there is no turbulence for the model to sustain, and `k` collapses toward zero away from
the jet. The message count is high only because it fires per time step per occurrence over
~12,000 steps.

`k` staying at ~0.054 in the jet core also means `ν_t` stays elevated — consistent with the
kOmegaSST arm's tray mean remaining ~2× the laminar one throughout, rather than drifting toward
it.

> **I got this wrong once before writing it down.** An earlier health check reported "zero
> `bounding` across both arms" — true only of the laminar arm, which has no `k` to bound. Checking
> a whole-matrix property on one arm and reporting it of both is its own small lesson.

## 4b. Phase 2 / Phase 3 readiness (checked 2026-08-15, alongside this matrix)

Phase 3 commits **86–150 h** of compute to `buoyantPimpleFoam` (CLAUDE.md §10.4), and that
solver path had **never once been executed**. Before trusting it, the dicts were inspected and
a deliberately tiny run (`--endTime 0.25 --avgStart 0.15`, 0.03 τ, ~64 steps) was generated as
`runs/p2_smoke_m0` purely to prove the path starts and does not diverge.

What the dict inspection confirmed:

| | |
|---|---|
| `0.orig/p` | `calculated` on all patches ✓ — §5.2 requires `p` be **derived** from `p_rgh`, never set independently |
| `0.orig/p_rgh` | `fixedFluxPressure` on the no-slip patches ✓ |
| `hood` heat load | `externalWallHeatFluxTemperature`, `mode power`, `Q 38.4` ✓ — §6.3 requires **P**, not `q`, so patch area is never double-counted |
| `floor`/`walls` | `zeroGradient` — adiabatic first cut, still the open question in §10.4 item 10 |
| `alphat` | `compressible::alphatWallFunction` ✓ |

### It failed on the first time step — `rhoFinal` was missing

The smoke test earned its keep immediately:

```
--> FOAM FATAL IO ERROR: (openfoam-2606)
Entry 'rhoFinal' not found in dictionary "system/fvSolution/solvers"
```

PIMPLE looks up `<field>Final` for the last outer corrector of **every** field it solves. The
transient `fvSolution` had `pFinal`, `p_rghFinal` and the `"(U|k|omega|e|h)Final"` regex — but
`rho` was written as a bare entry matching neither, so it had no `Final` variant.

**Phase 1 could never have caught this.** `pimpleFoam` is incompressible and does not solve
`rho` at all; the entry is only ever read by the buoyant solvers. The gap was invisible until
`buoyantPimpleFoam` was actually executed — which, before this, had never happened in the
project's history. `doc/FIRST_RUN.md` called it: *"Phase 2 is untested… Expect more of the same
class of dict error."*

Fixed by writing it as `"rho.*"`, so the plain and `Final` forms cannot drift apart again.
**After the fix the smoke test passes cleanly** — `End` reached, 0 `FOAM FATAL`, 0 `bounding`
messages over 99 steps.

#### It also gave the first buoyant cost anchor, and it is not encouraging

`buoyantPimpleFoam` ran at **20.3 s/step** on 4 ranks under heavy contention, against
**7.0 s/step** for `pimpleFoam` on the same mesh and rank count — so the buoyant solver costs
**≈ 2.9× per step**, from the extra energy equation and a stiffer pressure problem. Scaling the
clean 8-rank isothermal rate (2.53 s/step) by that factor gives ≈ 7.3 s/step, i.e.

> **~50 h per Phase 3 case ⇒ ~250 h (≈ 10 days) for the full 4-`g` sweep.**

That extrapolates across two different contention levels, so it is an order of magnitude rather
than a number — **take one clean 8-rank measurement before committing.** The practical
consequence is already in `sweep_gravity.sh`: run the two endpoints first
(`GVALS="0 9.81"`, ~4 days), and only fill in Lunar/Mars if 0 g and 1 g actually separate.

**The cost of not having run this:** `sweep_gravity.sh` would have generated its first case,
meshed it (~10 min), launched `buoyantPimpleFoam`, and died on time step 1 — then done the same
for every remaining `g` value, since the loop's failure handler prints a message and continues.
A whole overnight Phase 3 sweep would have produced zero time steps.

#### Both buoyant solvers now verified

| smoke test | result |
|---|---|
| `buoyantPimpleFoam` (Phase 2b / Phase 3) | `runs/p2_smoke_m0` — **End reached**, 99 steps, 0 `FOAM FATAL`, 0 `bounding` |
| `buoyantSimpleFoam` (Phase 2, the §5.1 roadmap solver) | `runs/p2_smoke_steady_m0` — **End reached**, 20 iterations, 0 `FOAM FATAL`, 0 `bounding` |

The steady arm was checked separately rather than assumed covered by the transient fix: SIMPLE
never reads `<field>Final` entries, so it was always going to survive the `rhoFinal` gap, and
confirming that is the point — it solves `Ux`, `h` (energy equation live) and `p_rgh`, on a mesh
whose total volume is 2.5300828e-3 m³ against `V_air` = 2.5302e-3, i.e. the tray slots are open.

Testing it at all required lifting a generator restriction: `--endTime` was rejected for steady
runs, so the only way to exercise `buoyantSimpleFoam` was to launch all 4000 iterations of it.
For a steady solver "time" *is* the iteration count, so capping it is exactly what a smoke test
needs. `--avgStart` is still correctly transient-only.

Two further things were fixed as a result of the same exercise:

1. **The generator mislabelled short runs.** It printed the `N_TAU_END` *constant* rather than
   the achieved ratio, so this 0.03 τ smoke test announced itself as `endTime 0.25 s (6.6 tau)`.
   It now computes `endTime/τ` and `avgStart/τ`, and warns below 4 τ that the run is a smoke
   test whose statistics are meaningless.
2. **The `0.orig.phase2/T` header quoted only Q = 5 m³/h figures** (22.9 K, "thermally viable
   would be ~5 W"). At the working Q = 1.25 those are 4× optimistic: 91.7 K and ~1.3 W. Both
   the template and CLAUDE.md §6.3 now carry the per-`Q` table.

## 4c. An open question the spectrum raises about `--jetRefine`

`--jetRefine` exists to resolve the **inlet shear layer**: with a top-hat BC on a plain cutout
the layer starts at zero thickness and is only resolved beyond `x_res = h²U/ν`, which the flag
cuts 4× for +9 % cells (CLAUDE.md §7). That reasoning is sound and unaffected by anything here.

But it was implicitly motivated by the idea that the shear layer drives the unsteadiness. The
spectrum says otherwise — **the instability is a chamber-scale recirculation wander at ≥ 5.4 s,
with 0.1 % of the power in the shear-layer/jet-column band.** So the flag may matter less for
*capturing the unsteadiness* than assumed, even though it still governs how the jet spreads,
which sets the recirculation that is unsteady.

**Not a conclusion — a question worth one controlled test**, and the matrix already contains
the arms to answer it: `m0_lam` (plain, `x_res` = 202 mm, shear layer never resolved) against
`m0_lam_jet` (`x_res` = 50.6 mm). If their flapping amplitude and timescale agree, `--jetRefine`
is buying jet-spreading accuracy rather than unsteadiness fidelity, and the +2.2× wall clock it
costs (2× steps as well as +9 % cells) can be spent elsewhere. If they disagree, the shear layer
matters after all. `m0_lam` is queued behind the primary arm precisely so this can be checked.

## 4d. Resume here — what to do when the runs finish

Everything below is set up and detached; nothing needs babysitting.

**Already running without a session:** both solvers (`nohup`), and
`scripts/queue_next_arm.sh` (PID in its own session, PPID 1) which launches the third arm on
cores 0–3 once `m0_lam_jet` prints `== done`. It refuses to launch if that arm failed.

**1. Check the runs landed.**

```bash
grep -c "^End" runs/p1_trans_q1p25_m0_*/log.pimpleFoam    # 1 each
validation/audit_cases.sh                                  # only p1_transient_m1 should be STALE
```

**2. Run the whole analysis.**

```bash
validation/phase1_report.sh 2>&1 | tee validation/phase1_report.txt
```

That covers the cross-case table with correlated-sample error bars, the discard-window sweep,
the spectrum, per-case statistics, and mean age of air on `phiMean` — then prints the CLAUDE.md
§9 acceptance checklist.

**3. Read it in this order, because three numbers gate the rest.**

| check | where | if it fails |
|---|---|---|
| `ageOutlet` ≈ 1.00 τ | §4 of the report | the age solve did not converge; `ageMean`/`ageHood` are meaningless |
| `N_eff` | §1, `N_eff` column | < 10 ⇒ the mean is not resolved. See the adequacy note in §4 — it may still answer the model question |
| spectral peak vs `1/T` | §2b | if the peak still sits at the window fundamental, the timescale is *still* unbracketed and no windowed statistic is trustworthy |

**4. Two questions the finished record can answer that this one could not.**

- **Does a characteristic period exist?** The 28.1 s window is 3× the longest record analysed so
  far and the first that could tell a slow oscillation from red noise. Until then, `T_int`,
  `N_eff` and the probe correlation are all bounded, not measured.
- **Does `--jetRefine` buy unsteadiness fidelity or only jet spreading?** Compare `m0_lam`
  against `m0_lam_jet` — see §4c. Worth knowing, because the flag costs 2.2× wall clock on every
  future transient.

**5. Do not re-derive the two retracted claims.** §4a records what they were, how they were
tested, and why they failed. Both came from statistics on windows shorter than the flow's own
timescale.

## 5. What this matrix does not settle

- **Transient mesh independence.** `m1 --jetRefine` is ~49 k steps at ~5 s/step ≈ **68 h** and
  was not run. Note `--jetRefine` costs 2× the *steps* as well as +9 % cells, so §7's "+25 %
  cells" understates it. The `m0`/`m1` agreement in §9.6 is steady-iteration evidence at
  `Q` = 5, and does not transfer to a time average at `Q` = 1.25 without being checked.
- **Phase 2.** Isothermal only. The hood carries the LED load and its `y⁺` doubles at m0.
- **The operating point.** `Q` = 1.25 m³/h is still a placeholder pending the LD3007MS Δp–Q
  curve (CLAUDE.md §10.2 item 1). Every number here is conditional on it.
