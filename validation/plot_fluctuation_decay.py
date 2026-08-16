#!/usr/bin/env python3
"""Does the fluctuation SUSTAIN or DECAY? -- the test that separates a genuinely
unsteady flow from one relaxing to a steady state.

    python3 validation/plot_fluctuation_decay.py runs/p1_trans_* [--out NAME]

Why this exists
---------------
A time average and an RMS computed over the whole record cannot tell these two
cases apart:

    (a) a sustained oscillation of constant amplitude
    (b) a decaying transient that ends steady

Both give "RMS = 9 %". Only (a) is an unsteady flow; (b) is a steady flow that
had not finished settling. The distinction decides whether `pimpleFoam` is
*required* (CLAUDE.md 5.1) or merely being used to reach a steady answer slowly.

So: slide a window of one dominant period along the record and plot the RMS
within each window. Sustained -> flat. Relaxing -> monotone decay.

This is deliberately an AMPLITUDE measure, not a correlation. CLAUDE.md 10.3
records a retracted claim ("kOmegaSST suppresses the instability") that rested on
probe correlation `r` over 2 s windows, and died because `r` on a window shorter
than the flow's own timescale tracks the oscillation's PHASE rather than whether
it exists. An amplitude ratio across many windows does not have that failure
mode -- a decay of 30x across six successive windows cannot be a phase artefact.

Read the RATIO (first window -> last), not any single number. And always run it
on both arms: the comparison is what makes it evidence rather than an assertion.
"""

import sys
import pathlib
import importlib.util

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = pathlib.Path(__file__).parent
_spec = importlib.util.spec_from_file_location("pt", HERE / "plot_transient.py")
pt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pt)

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"

PROBES = ["jet core", "mid-chamber", "off-axis +30", "off-axis -30", "hood"]
# The two that carry the chamber-scale recirculation. The jet core and the
# on-axis probe sit in the jet, which is steady to four figures in BOTH arms
# (CLAUDE.md 10.3), so their RMS is ~0 and tells you nothing either way.
INTEREST = [4, 3]


def windowed_rms(t, y, t0, t1, width, step):
    """RMS as a percentage of the local mean, in windows of `width`."""
    out = []
    s = t0
    while s + width <= t1 + 1e-9:
        m = (t >= s) & (t <= s + width)
        if m.sum() >= 50:
            seg = y[m]
            out.append((s + width / 2, 100 * seg.std() / abs(seg.mean())))
        s += step
    return np.array(out)


def analyse(case, width=None):
    case = pathlib.Path(case).resolve()
    t, a = pt.read_probes(case)
    if t is None:
        return None
    tau = pt.tau(case)
    t0 = pt.avg_start(case)
    t1 = float(t.max())
    # One dominant period is the natural window. Fall back to ~1.3 tau, which is
    # what both arms measure (9.35 s and 10.49 s against tau = 7.29 s).
    w = width or 1.3 * tau
    mag = np.linalg.norm(a, axis=2)
    res = {}
    for i in INTEREST:
        res[PROBES[i]] = windowed_rms(t, mag[:, i], t0, t1, w, w / 2)
    return dict(name=case.name, tau=tau, t0=t0, t1=t1, width=w, probes=res)


def report(cases):
    print(f"\n{'case':<30}{'probe':<15}{'window':>9}{'first':>9}{'last':>9}"
          f"{'ratio':>9}  verdict")
    print("-" * 92)
    for c in cases:
        for name, arr in c["probes"].items():
            if len(arr) < 3:
                print(f"{c['name']:<30}{name:<15}  too few windows")
                continue
            first, last = arr[0, 1], arr[-1, 1]
            ratio = last / first if first else np.nan
            verdict = ("DECAYING -> steady" if ratio < 0.5 else
                       "growing" if ratio > 2.0 else "sustained")
            print(f"{c['name']:<30}{name:<15}{c['width']:9.1f}"
                  f"{first:9.2f}{last:9.2f}{ratio:9.2f}  {verdict}")
    print("-" * 92)
    print("ratio << 1 => the 'unsteadiness' is a decaying transient, not a")
    print("sustained oscillation, and the flow is heading for a steady state.")
    print("Compare arms: a ratio near 1 in one and << 1 in the other is a")
    print("MODEL effect, not a startup artefact shared by both.")


def figure(cases, out):
    fig, ax = plt.subplots(1, len(INTEREST), figsize=(11, 4.2), facecolor=SURFACE)
    ax = np.atleast_1d(ax)
    for k, i in enumerate(INTEREST):
        name = PROBES[i]
        a = ax[k]
        a.set_facecolor(SURFACE)
        for j, c in enumerate(cases):
            arr = c["probes"].get(name)
            if arr is None or not len(arr):
                continue
            a.plot(arr[:, 0] / c["tau"], arr[:, 1], "o-", color=SERIES[j % 4],
                   label=c["name"].replace("p1_trans_q1p25_", ""), lw=1.8, ms=4)
        a.set_title(f"{name} probe", color=INK, fontsize=11)
        a.set_xlabel("window centre  [residence times $\\tau$]", color=INK_2, fontsize=9)
        a.set_ylabel("fluctuation RMS  [% of local mean]", color=INK_2, fontsize=9)
        a.set_yscale("log")
        a.grid(alpha=0.25, lw=0.6)
        a.tick_params(colors=INK_2, labelsize=8)
        for s in a.spines.values():
            s.set_color("#d8d6d0")
    ax[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Sustained oscillation vs decaying transient — "
                 "windowed fluctuation amplitude", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"\nwrote {out}")


def main(argv):
    out = HERE / "fluctuation_decay.png"
    dirs = []
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = HERE / argv[i + 1]
            i += 2
        else:
            dirs.append(argv[i])
            i += 1
    if not dirs:
        sys.exit(__doc__)
    cases = [c for c in (analyse(d) for d in sorted(dirs)) if c]
    if not cases:
        sys.exit("no case had probe output")
    report(cases)
    figure(cases, out)


if __name__ == "__main__":
    main(sys.argv[1:])
