#!/usr/bin/env python3
"""Cross-case comparison of Phase 1 transient runs.

    python3 validation/compare_transients.py runs/p1_trans_* [--out NAME]

plot_transient.py answers "what did THIS case do". This answers the three
questions the Phase 1 matrix exists to settle, all of which need more than one
case side by side:

    mesh independence   m0+jetRefine  vs  m1+jetRefine    (same shear family)
    numerical damping   m0 plain      vs  m0+jetRefine    (same mesh level)
    model spread        laminar       vs  kOmegaSST       (same mesh)

Why this is not just plot_transient in a loop
---------------------------------------------
A time average of a fluctuating signal has an UNCERTAINTY, and comparing two
means without it is how a mesh study talks itself into a conclusion. CLAUDE.md
9.6 says exactly this about the existing m0/m1 comparison -- "It is not a GCI.
These are SIMPLE-iteration averages of a run that never converged... Strong
indicator, not proof -- the rigorous version needs transient time-averages."
This is that rigorous version, so it has to carry the error bar.

The error bar is NOT sd/sqrt(N). Successive samples of a flapping jet are
strongly correlated -- at ~1 kHz sampling and a flapping period of order a
second, a thousand consecutive samples carry roughly ONE independent look at the
flow. Using the raw N would understate the uncertainty by ~sqrt(1000) = 30x and
make every difference look significant. So the standard error here is

    SE = sd / sqrt(N_eff),      N_eff = N * dt / (2 * T_int)

with T_int the integral timescale, obtained by integrating the autocorrelation
to its first zero crossing (the standard truncation -- the tail past that point
is noise and integrating through it makes T_int a random number).

Two means are then reported as DISTINGUISHABLE only if they differ by more than
the combined standard error. That is the honest form of "the mesh is/is not the
limiting error".
"""

import sys
import pathlib
import importlib.util

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).parent

# Reuse the readers rather than restating the file formats. plot_transient.py is
# not importable as a module name (it is a script in a non-package dir), so load
# it by path -- this keeps ONE definition of how a function object's output is
# parsed, including the restart-directory concatenation, which is easy to get
# subtly wrong a second time.
_spec = importlib.util.spec_from_file_location("plot_transient", HERE / "plot_transient.py")
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8880"


def integral_timescale(y, dt):
    """Integral timescale of a signal, by autocorrelation to first zero crossing.

    Returns (T_int, N_eff_factor). The truncation at the first zero crossing is
    deliberate: the autocorrelation of a finite record is itself noisy at large
    lag, and integrating the full tail turns T_int into a random walk. Truncating
    is the standard estimator and biases T_int slightly LOW, i.e. it errs toward
    a larger N_eff and a SMALLER error bar -- so any 'indistinguishable' verdict
    from this function is conservative in the direction that matters.
    """
    y = np.asarray(y, dtype=float)
    y = y - y.mean()
    n = len(y)
    if n < 16 or y.std() == 0:
        return np.nan, np.nan
    # Unbiased-ish normalised autocorrelation via FFT.
    nfft = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(y, nfft)
    ac = np.fft.irfft(f * np.conj(f), nfft)[:n].real
    ac /= ac[0]
    zero = np.argmax(ac < 0) if (ac < 0).any() else n
    if zero < 2:
        return 0.0, float(n)
    # Trapezoidal integral of the autocorrelation up to the first zero.
    t_int = np.trapezoid(ac[:zero], dx=dt) if hasattr(np, "trapezoid") \
        else np.trapz(ac[:zero], dx=dt)
    if t_int <= 0:
        return 0.0, float(n)
    n_eff = n * dt / (2.0 * t_int)
    return t_int, max(n_eff, 1.0)


def stats(t, y):
    """Mean, RMS, and the standard error of the MEAN accounting for correlation."""
    dt = float(np.median(np.diff(t)))
    mu = float(y.mean())
    sd = float(y.std(ddof=1))
    t_int, n_eff = integral_timescale(y, dt)
    se = sd / np.sqrt(n_eff) if np.isfinite(n_eff) else np.nan
    return dict(mean=mu, sd=sd, rms_pct=100 * sd / abs(mu) if mu else np.nan,
                t_int=t_int, n_eff=n_eff, se=se,
                se_pct=100 * se / abs(mu) if mu else np.nan,
                n=len(y), dt=dt, span=float(t[-1] - t[0]))


def peak_frequency(t, y):
    """Dominant frequency of the fluctuation, on a uniformly resampled signal."""
    if len(y) < 64:
        return np.nan
    f, p, _ = pt.psd(t, y)
    return float(f[np.argmax(p)])


def load(case, t0_override=None):
    """Everything needed for one case, restricted to its averaging window.

    t0_override replaces the case's own `timeStart`. Two uses, both legitimate:
    checking the pipeline on a partially-complete run before it reaches its real
    averaging window, and sweeping the discard length to show the reported mean
    is insensitive to it -- which is the evidence that the start-from-rest
    transient really has been thrown away, rather than an assertion that it has.
    """
    case = pathlib.Path(case).resolve()
    t0 = pt.avg_start(case) if t0_override is None else float(t0_override)
    tau = pt.tau(case)
    ts, tray = pt.read_series(case, "traySignal")
    if ts is None:
        return None
    tray = tray[:, 0]
    win = ts >= t0
    if win.sum() < 32:
        print(f"  !! {case.name}: only {win.sum()} samples past t0 = {t0} s -- skipping")
        return None

    d = dict(name=case.name, path=case, t0=t0, tau=tau,
             t=ts[win], tray=tray[win], t_all=ts, tray_all=tray,
             end=float(ts[-1]))
    d["tray_stats"] = stats(d["t"], d["tray"])
    d["f_peak"] = peak_frequency(d["t"], d["tray"])
    d["n_tau"] = (d["end"] - t0) / tau if tau else np.nan

    # Cell count, from the mesh the run actually used.
    ck = case / "log.checkMesh"
    d["cells"] = np.nan
    if ck.exists():
        for line in ck.read_text().splitlines():
            s = line.strip()
            if s.startswith("cells:"):
                d["cells"] = int(s.split()[1])
                break

    # Off-axis probe pair -- the flapping signature. An area average over the
    # tray cannot show a lateral oscillation; an anti-phase pair can.
    tp, up = pt.read_probes(case)
    d["anti"] = np.nan
    if tp is not None and up.shape[1] >= 4:
        wp = tp >= t0
        if wp.sum() > 32:
            a = up[wp, 2, 1]
            b = up[wp, 3, 1]
            if a.std() > 0 and b.std() > 0:
                d["anti"] = float(np.corrcoef(a - a.mean(), b - b.mean())[0, 1])

    # Slot flux and port balance, if present.
    for fo, key, col in [("traySlotFlux", "slot", 0),
                         ("inletFlux", "qin", 0),
                         ("outletFlux", "qout", 0)]:
        tt, vv = pt.read_series(case, fo)
        d[key] = None
        if tt is not None:
            m = tt >= t0
            if m.sum() > 4:
                d[key] = stats(tt[m], vv[m, col])
    return d


def fmt(v, spec=".4g"):
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) \
        else format(v, spec)


def report(cases):
    print("\n" + "=" * 108)
    print("TRANSIENT COMPARISON -- tray-plane mean speed, time-averaged")
    print("=" * 108)
    print(f"{'case':<30}{'cells':>9}{'tau':>7}{'window':>9}"
          f"{'mean':>11}{'+-SE':>10}{'RMS%':>8}{'T_int':>8}{'N_eff':>8}{'f_pk':>8}{'anti':>7}")
    print(f"{'':<30}{'':>9}{'[s]':>7}{'[tau]':>9}{'[m/s]':>11}{'[m/s]':>10}"
          f"{'':>8}{'[s]':>8}{'':>8}{'[Hz]':>8}{'r':>7}")
    print("-" * 108)
    for c in cases:
        s = c["tray_stats"]
        print(f"{c['name']:<30}{fmt(c['cells'], '.0f'):>9}{fmt(c['tau'], '.2f'):>7}"
              f"{fmt(c['n_tau'], '.1f'):>9}"
              f"{fmt(s['mean'], '.5f'):>11}{fmt(s['se'], '.1e'):>10}"
              f"{fmt(s['rms_pct'], '.1f'):>8}{fmt(s['t_int'], '.3f'):>8}"
              f"{fmt(s['n_eff'], '.0f'):>8}{fmt(c['f_peak'], '.2f'):>8}"
              f"{fmt(c.get('anti'), '.2f'):>7}")
    print("-" * 108)
    print("SE is the standard error of the MEAN with correlated samples "
          "(N_eff = N*dt/2T_int), NOT sd/sqrt(N).")
    print("anti = correlation of the two off-axis probes.")
    print("   ⚠ NOT a state indicator unless the window spans MANY dominant")
    print("     timescales. Measured 2026-08-15: with a >= 8.9 s timescale, r over")
    print("     successive 2 s windows swung +0.99 / -0.99 / -0.13 in the SAME run.")
    print("     A short window samples the oscillation's PHASE, not whether it")
    print("     exists. Check the T_int and window columns before reading it.")

    # --- are these cases even comparable? ----------------------------------
    # Each case's averaging window runs from its own timeStart to wherever its
    # record currently ENDS, so two runs at different completion levels are
    # averaged over different stretches of physical time. That is not a
    # like-for-like comparison, and on this chamber it is actively misleading:
    # the jet instability onsets at ~1.05 tau (see validation/transient_matrix.md),
    # so an arm that has only reached 0.9 tau looks perfectly steady while one at
    # 1.3 tau is flapping -- a difference of TIME, read as a difference of
    # physics. Observed 2026-08-15 between the laminar and kOmegaSST arms.
    ends = [c["end"] for c in cases]
    if len(cases) > 1 and max(ends) > 0 and (max(ends) - min(ends)) / max(ends) > 0.05:
        print()
        print("!! WARNING -- these cases are NOT at the same simulated time:")
        for c in sorted(cases, key=lambda c: c["end"]):
            ntau = f"{c['end'] / c['tau']:.2f} tau" if c["tau"] else "?"
            print(f"     {c['name']:<30} ends at {c['end']:8.3f} s  ({ntau})")
        print("   Their averaging windows therefore cover different stretches of")
        print("   physical time, and the comparison below mixes a time difference")
        print("   with a mesh/model difference. Wait for the shorter runs, or")
        print("   restrict every case to a common window by hand before quoting")
        print("   any of this as a model or mesh effect.")

    # Pairwise: is the difference bigger than the combined uncertainty?
    if len(cases) > 1:
        print("\n" + "=" * 108)
        print("PAIRWISE -- is the difference in the mean larger than the uncertainty?")
        print("=" * 108)
        print(f"{'A':<26}{'B':<26}{'diff':>10}{'diff %':>9}"
              f"{'combined SE':>13}{'ratio':>8}  verdict")
        print("-" * 108)
        for i in range(len(cases)):
            for j in range(i + 1, len(cases)):
                a, b = cases[i], cases[j]
                sa, sb = a["tray_stats"], b["tray_stats"]
                diff = sb["mean"] - sa["mean"]
                comb = np.hypot(sa["se"], sb["se"])
                ratio = abs(diff) / comb if comb else np.nan
                pct = 100 * diff / abs(sa["mean"]) if sa["mean"] else np.nan
                verdict = ("INDISTINGUISHABLE" if ratio < 2
                           else "distinguishable" if ratio < 5
                           else "STRONGLY different")
                print(f"{a['name']:<26}{b['name']:<26}{diff:>10.5f}{pct:>8.1f}%"
                      f"{comb:>13.2e}{ratio:>8.1f}  {verdict}")
        print("-" * 108)
        print("ratio < 2 -> the two runs agree to within their own sampling noise;")
        print("a mesh/model difference is only real if it clears its error bar.")


def figure(cases, out):
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8.5))
    fig.patch.set_facecolor(SURFACE)
    ax = axes.ravel()

    for k, c in enumerate(cases):
        col = SERIES[k % len(SERIES)]
        # 1. tray signal, full history, normalised to residence times
        tt = c["t_all"] / c["tau"] if c["tau"] else c["t_all"]
        ax[0].plot(tt, c["tray_all"], color=col, linewidth=0.75,
                   alpha=0.85, label=c["name"].replace("p1_trans_q1p25_", ""))
        # 2. spectrum over the averaging window
        if len(c["tray"]) > 64:
            f, p, _ = pt.psd(c["t"], c["tray"])
            ax[1].loglog(f, p, color=col, linewidth=1.0, alpha=0.9)
        # 3. mean with error bar
        s = c["tray_stats"]
        ax[2].errorbar(k, s["mean"], yerr=s["se"], fmt="o", color=col,
                       capsize=5, markersize=7, linewidth=1.6)
        # RMS band behind it, to show the fluctuation the mean sits inside
        ax[2].add_patch(plt.Rectangle((k - 0.22, s["mean"] - s["sd"]), 0.44,
                                      2 * s["sd"], color=col, alpha=0.13, linewidth=0))
        # 4. RMS %
        ax[3].bar(k, s["rms_pct"], color=col, width=0.55)

    ax[0].axvline(cases[0]["t0"] / cases[0]["tau"] if cases[0]["tau"] else cases[0]["t0"],
                  color=INK_MUTED, linewidth=1.2, linestyle=(0, (5, 4)))
    ax[0].legend(frameon=False, fontsize=8, labelcolor=INK_2, loc="upper right")
    pt.style(ax[0], "Tray-plane mean speed (dashed = averaging starts)",
             "|U|  [m/s]", "time  [residence times tau]")
    pt.style(ax[1], "Spectra over the averaging window", "power  [-]", "frequency  [Hz]")

    labels = [c["name"].replace("p1_trans_q1p25_", "") for c in cases]
    for a, ttl, yl in [(ax[2], "Time-averaged mean +- standard error\n"
                               "(band = +-1 RMS, the fluctuation it sits inside)",
                        "|U|  [m/s]"),
                       (ax[3], "Fluctuation level", "RMS  [% of mean]")]:
        a.set_xticks(range(len(cases)))
        a.set_xticklabels(labels, fontsize=8, rotation=12, ha="right")
        pt.style(a, ttl, yl)

    fig.suptitle("Phase 1 transient matrix -- Q = 1.25 m3/h", color=INK,
                 fontsize=13, x=0.055, ha="left", y=0.985)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"\nwrote {out}")


def window_sweep(case_dir):
    """Is the reported mean sensitive to how much startup we discard?

    The averaging window is set to 2.75 tau on the argument that a start-from-
    rest field needs ~3 flow-throughs to forget its initial condition. That is a
    rule of thumb, and this checks it against the actual signal: if the mean
    still drifts as the discard grows, the run has not forgotten its start and
    the average is contaminated no matter how long the record is.
    """
    c0 = load(case_dir, t0_override=0.0)
    if not c0:
        return
    tau = c0["tau"] or 1.0
    t_end = c0["t_all"][-1]
    print(f"\n{'=' * 78}\nDISCARD-WINDOW SENSITIVITY -- {c0['name']}\n{'=' * 78}")
    print(f"{'discard':>10}{'discard':>10}{'samples':>10}{'mean':>12}{'+-SE':>11}{'RMS%':>8}")
    print(f"{'[tau]':>10}{'[s]':>10}{'':>10}{'[m/s]':>12}{'[m/s]':>11}{'':>8}")
    print("-" * 78)
    for n in (0.5, 1.0, 1.5, 2.0, 2.75, 3.5, 4.0):
        t0 = n * tau
        if t0 >= t_end * 0.9:
            continue
        c = load(case_dir, t0_override=t0)
        if not c:
            continue
        s = c["tray_stats"]
        print(f"{n:>10.2f}{t0:>10.2f}{s['n']:>10d}{s['mean']:>12.5f}"
              f"{s['se']:>11.2e}{s['rms_pct']:>8.1f}")
    print("-" * 78)
    print("The mean should stop moving well before the 2.75 tau the generator uses.")
    print("If it is still drifting at 2.75, the run has not forgotten its initial field.")


def spectrum_report(case_dir, t_from=None):
    """Where is the unsteadiness in frequency, and is the peak even resolved?

    Two questions, both easy to get wrong:

    1. **Is the reported peak a measurement?** A finite record cannot resolve
       anything below 1/T. If the spectral peak sits AT 1/T it is the window
       fundamental, not a property of the flow -- all you may conclude is that
       the timescale is >= T. Measured 2026-08-15 on this chamber, the peak sat
       exactly at 1/T for records of 3.6 s and then 5.3 s: the motion is slower
       than anything sampled so far.

    2. **Which band carries the power?** `functions/transientMonitors` used to
       justify its sample rate against a jet-column mode at St ~ 0.3 (16.6 Hz at
       Q = 1.25). Measured, that band holds 0.1-0.2 % of the power while >94 %
       sits below 1 Hz -- a slow chamber-filling recirculation, not a jet
       instability. Nyquist is ~255 Hz, so the emptiness is real.

    The practical consequence is that RECORD LENGTH, not sample rate, is the
    binding constraint on these runs.
    """
    c = load(case_dir, t0_override=t_from if t_from is not None else 0.0)
    if not c:
        return
    tp, up = pt.read_probes(c["path"])
    if tp is None or up.shape[1] < 4:
        print(f"{c['name']}: no jetProbes output")
        return
    t0 = t_from if t_from is not None else c["t0"]
    m = tp >= t0
    if m.sum() < 128:
        print(f"{c['name']}: only {m.sum()} probe samples after t = {t0:g} s")
        return

    # Lateral flapping signal: the DIFFERENCE of the two off-axis probes. A
    # symmetric jet cancels; a flapping one does not.
    sig = up[m, 2, 1] - up[m, 3, 1]
    T = float(tp[m][-1] - tp[m][0])
    f, p, dt = pt.psd(tp[m], sig)
    pk = float(f[np.argmax(p)])
    fmin = 1.0 / T
    tau = c["tau"]

    print(f"\n=== spectrum: {c['name']}")
    print(f"  record {tp[m][0]:.2f}-{tp[m][-1]:.2f} s = {T:.2f} s"
          + (f" ({T / tau:.2f} tau)" if tau else "")
          + f", {m.sum()} samples, Nyquist {1 / (2 * dt):.0f} Hz")
    print(f"  lowest resolvable frequency 1/T = {fmin:.3f} Hz")
    print(f"  spectral peak                   = {pk:.3f} Hz  (period {1 / pk:.2f} s)")
    if abs(pk - fmin) / fmin < 0.15:
        print(f"  !! RESOLUTION-LIMITED -- the peak IS the window fundamental.")
        print(f"     Conclude only: the dominant timescale is >= {T:.1f} s"
              + (f" ({T / tau:.2f} tau)." if tau else "."))
        print(f"     Do not quote {1 / pk:.2f} s as a period. Lengthen the record.")
        print(f"     Do not fit a spectral slope either: with < 1 cycle in the")
        print(f"     record an FFT is fitting a trend, and any trend gives a steep")
        print(f"     slope. Red noise and an unresolved oscillation look identical.")
    else:
        print(f"  -> resolved: the peak is above the window fundamental.")

    tot = p.sum()
    print("  power by band:")
    for lo, hi, lbl in [(0.0, 1.0, "chamber-scale (periods > 1 s)"),
                        (1.0, 5.0, "intermediate"),
                        (5.0, 30.0, "St~0.3 jet-column band"),
                        (30.0, 1e9, "high frequency")]:
        b = (f >= lo) & (f < hi)
        print(f"    {lbl:<32} {100 * p[b].sum() / tot:5.1f} %")

    if tau:
        win = 3.85 * tau        # the 6.6 - 2.75 tau averaging window
        # Which timescale to divide by depends on whether the peak is resolved.
        # While it sits at the window fundamental, all that is known is
        # "timescale >= record length", so the record length is the honest (and
        # conservative) proxy. Once the peak clears the fundamental the PERIOD is
        # the real quantity, and using the record length instead understates the
        # cycle count -- it reported ~1 cycle where the resolved period gives
        # ~2.6. Fixed 2026-08-15, the moment the peak first resolved.
        if abs(pk - fmin) / fmin < 0.15:
            print(f"  timescale still unresolved, so using the record length as a "
                  f"lower bound:")
            print(f"  the 6.6-tau averaging window is {win:.1f} s "
                  f"=> at most ~{win / T:.0f} independent cycles.")
        else:
            per = 1.0 / pk
            print(f"  resolved period {per:.2f} s = {per / tau:.2f} tau;")
            print(f"  the 6.6-tau averaging window is {win:.1f} s "
                  f"=> ~{win / per:.1f} independent cycles.")
            print(f"  ⚠ frequency resolution is {fmin:.3f} Hz, so with the peak at "
                  f"{pk:.3f} Hz the period")
            print(f"    is only pinned to within about a bin -- treat "
                  f"{per:.1f} s as order-of-magnitude.")


def main(argv):
    out = HERE / "transient_matrix.png"
    t0_override = None
    sweep = False
    spectrum = False
    dirs = []
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = HERE / argv[i + 1]
            i += 2
        elif argv[i] == "--from":
            t0_override = float(argv[i + 1])
            i += 2
        elif argv[i] == "--window-sweep":
            sweep = True
            i += 1
        elif argv[i] == "--spectrum":
            spectrum = True
            i += 1
        else:
            dirs.append(argv[i])
            i += 1
    if not dirs:
        sys.exit(__doc__)
    if spectrum:
        for d in sorted(dirs):
            spectrum_report(d, t0_override)
        return
    if sweep:
        for d in sorted(dirs):
            window_sweep(d)
        return
    cases = [c for c in (load(d, t0_override) for d in sorted(dirs)) if c]
    if not cases:
        sys.exit("no case had usable traySignal output -- have the runs finished?")
    if t0_override is not None:
        print(f"\n!! averaging window OVERRIDDEN to start at t = {t0_override} s "
              f"-- these are NOT the case's own statistics")
    report(cases)
    figure(cases, out)


if __name__ == "__main__":
    main(sys.argv[1:])
