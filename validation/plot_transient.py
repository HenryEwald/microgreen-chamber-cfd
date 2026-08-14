#!/usr/bin/env python3
"""Transient analysis for a Phase 1/2b pimpleFoam case.

A transient run's answer is a TIME AVERAGE plus a fluctuation level, plus the
frequency content that made a steady run impossible in the first place. That is
what this produces:

    python3 validation/plot_transient.py runs/p1_transient_m1

Writes validation/<case-id>_transient.png and prints the statistics table.

Two things worth knowing about the data:

  * `adjustTimeStep yes` means the samples are NOT uniformly spaced in time, so
    everything spectral has to be resampled onto a uniform grid first. Running an
    FFT straight on the raw series would smear the very peak being looked for.
  * The averaging window comes from `timeStart` in functions/transientMonitors,
    so it is read out of the case rather than assumed here -- if the two
    disagreed, the mean would be quietly wrong.
"""

import re
import sys
import glob
import pathlib

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Reference categorical palette, light mode, slots in order. Panels are
# independent, so each restarts at slot 1. Validator is a node script and there
# is no JS runtime on this box (see plot_convergence.py) -- these are the
# documented slots, unmodified, on the adjacent pairlist.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8880"


def read_series(case, fo_name, fname="surfaceFieldValue.dat", ncols=1):
    """Concatenate a function object's output across restart directories.

    postProcessing/<fo>/<startTime>/<file> -- a resumed run adds a directory
    rather than appending, and they must go together in time order.
    """
    paths = sorted(
        glob.glob(str(case / "postProcessing" / fo_name / "*" / fname)),
        key=lambda p: float(pathlib.Path(p).parent.name),
    )
    if not paths:
        return None, None
    t, v = [], []
    for p in paths:
        for line in pathlib.Path(p).read_text().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.replace("(", " ").replace(")", " ").split()
            t.append(float(parts[0]))
            v.append([float(x) for x in parts[1 : 1 + ncols]])
    t = np.array(t)
    v = np.array(v)
    # A restart re-writes overlapping times; keep the last value for each.
    _, keep = np.unique(t[::-1], return_index=True)
    keep = len(t) - 1 - keep
    return t[keep], v[keep]


def read_probes(case, fo_name="jetProbes", field="U"):
    """probes writes `time (ux uy uz) (ux uy uz) ...`, one column per probe."""
    paths = sorted(
        glob.glob(str(case / "postProcessing" / fo_name / "*" / field)),
        key=lambda p: float(pathlib.Path(p).parent.name),
    )
    if not paths:
        return None, None
    t, rows = [], []
    for p in paths:
        for line in pathlib.Path(p).read_text().splitlines():
            if line.startswith("#") or not line.strip():
                continue
            nums = [float(x) for x in line.replace("(", " ").replace(")", " ").split()]
            t.append(nums[0])
            rows.append(nums[1:])
    t = np.array(t)
    a = np.array(rows)
    return t, a.reshape(len(t), -1, 3)


def avg_start(case):
    """Read the averaging window out of the case, don't assume it."""
    txt = (case / "system/functions/transientMonitors").read_text()
    m = re.search(r"^\s*timeStart\s+([0-9.eE+-]+);", txt, re.M)
    return float(m.group(1)) if m else 0.0


def psd(t, y):
    """Power spectral density on a uniformly resampled signal.

    adjustTimeStep gives non-uniform samples; resample at the median rate so the
    frequency axis means something.
    """
    dt = np.median(np.diff(t))
    tu = np.arange(t[0], t[-1], dt)
    yu = np.interp(tu, t, y)
    yu = yu - yu.mean()
    yu *= np.hanning(len(yu))  # reduce leakage from the finite window
    f = np.fft.rfftfreq(len(yu), dt)
    p = np.abs(np.fft.rfft(yu)) ** 2
    return f[1:], p[1:], dt  # drop DC


def style(ax, title, ylabel, xlabel=None):
    ax.set_title(title, color=INK, fontsize=10.5, loc="left", pad=8)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.grid(True, color=INK_MUTED, alpha=0.18, linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK_MUTED)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK_2, labelsize=8.5, length=3, width=0.8)
    ax.set_facecolor(SURFACE)


def main(case_dir):
    case = pathlib.Path(case_dir).resolve()
    t0 = avg_start(case)
    out = pathlib.Path(__file__).parent / f"{case.name}_transient.png"

    ts, tray = read_series(case, "traySignal")
    if ts is None:
        sys.exit(f"no traySignal output under {case}/postProcessing -- has it run?")
    tray = tray[:, 0]
    win = ts >= t0

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    fig.patch.set_facecolor(SURFACE)
    ax = axes.ravel()

    # --- 1. the tray signal ------------------------------------------------
    ax[0].plot(ts, tray, color=SERIES[0], linewidth=0.9, alpha=0.85)
    if win.sum() > 10:
        m, sd = tray[win].mean(), tray[win].std()
        ax[0].axhline(m, color=SERIES[1], linewidth=1.6)
        ax[0].axhspan(m - sd, m + sd, color=SERIES[1], alpha=0.15, linewidth=0)
        ax[0].annotate(
            f"mean {m:.4f} m/s,  RMS {100 * sd / m:.1f}%",
            xy=(ts[win][0], m),
            xytext=(6, 8),
            textcoords="offset points",
            color=INK_2,
            fontsize=9,
        )
    ax[0].axvline(t0, color=INK_MUTED, linewidth=1.2, linestyle=(0, (5, 4)))
    ax[0].annotate(
        f"averaging starts {t0:g} s",
        xy=(t0, ax[0].get_ylim()[1]),
        xytext=(-4, -12),
        textcoords="offset points",
        color=INK_2,
        fontsize=8,
        ha="right",
    )
    style(ax[0], "Tray-plane mean speed vs time", "|U|  [m/s]", "time  [s]")

    # --- 2. spectrum of the tray signal ------------------------------------
    if win.sum() > 64:
        f, p, dt = psd(ts[win], tray[win])
        ax[1].loglog(f, p, color=SERIES[0], linewidth=1.1)
        pk = f[np.argmax(p)]
        ax[1].axvline(pk, color=SERIES[1], linewidth=1.4, linestyle=(0, (5, 4)))
        ax[1].annotate(
            f"peak {pk:.2f} Hz  (period {1 / pk:.2f} s)",
            xy=(pk, p.max()),
            xytext=(8, -4),
            textcoords="offset points",
            color=INK_2,
            fontsize=9,
        )
        style(ax[1], "Spectrum of the tray signal", "power  [-]", "frequency  [Hz]")

    # --- 3. off-axis probe pair -- the flapping evidence -------------------
    tp, up = read_probes(case)
    if tp is not None and up.shape[1] >= 4:
        wp = tp >= t0
        for slot, (idx, name) in enumerate([(2, "x = +30 mm"), (3, "x = -30 mm")]):
            ax[2].plot(
                tp[wp],
                up[wp, idx, 1],  # y-component: the through-flow direction
                color=SERIES[slot],
                linewidth=0.9,
                label=name,
            )
        ax[2].legend(
            frameon=False, fontsize=8.5, labelcolor=INK_2, loc="upper right", ncol=2
        )
        style(
            ax[2],
            "Off-axis probes, mid-chamber  (anti-phase = the jet is flapping)",
            "U_y  [m/s]",
            "time  [s]",
        )

        # --- 4. spectrum of the jet-core probe -----------------------------
        if wp.sum() > 64:
            core = np.linalg.norm(up[wp, 0, :], axis=1)
            f2, p2, _ = psd(tp[wp], core)
            ax[3].loglog(f2, p2, color=SERIES[0], linewidth=1.1)
            pk2 = f2[np.argmax(p2)]
            ax[3].axvline(pk2, color=SERIES[1], linewidth=1.4, linestyle=(0, (5, 4)))
            ax[3].annotate(
                f"peak {pk2:.2f} Hz",
                xy=(pk2, p2.max()),
                xytext=(8, -4),
                textcoords="offset points",
                color=INK_2,
                fontsize=9,
            )
            style(ax[3], "Spectrum at the jet core probe", "power  [-]", "frequency  [Hz]")

    fig.suptitle(
        f"{case.name} -- transient statistics",
        color=INK,
        fontsize=13,
        x=0.055,
        ha="left",
        y=0.985,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"wrote {out}\n")

    # --- table view --------------------------------------------------------
    print(f"averaging window: {t0:g} s -> {ts[-1]:g} s "
          f"({(ts[-1] - t0) / 1.82:.1f} residence times), {win.sum()} samples")
    print(f"median time step: {np.median(np.diff(ts)):.3e} s\n")
    print(f"{'quantity':<34}{'mean':>13}{'RMS':>13}{'RMS %':>9}{'min':>13}{'max':>13}")

    rows = [("tray-plane mean speed [m/s]", tray[win])]
    for fo, label, col in [
        ("ageMean", "age of air, volume mean [s]", 0),
        ("ageMax", "age of air, max [s]", 0),
    ]:
        tt, vv = read_series(case, fo, "volFieldValue.dat")
        if tt is not None and (tt >= t0).sum():
            rows.append((label, vv[tt >= t0, col]))
    tt, vv = read_series(case, "traySlotFlux")
    if tt is not None and (tt >= t0).sum():
        rows.append(("tray slot flux [m3/s]", vv[tt >= t0, 0]))

    for label, v in rows:
        sd = v.std()
        mu = v.mean()
        pct = 100 * sd / abs(mu) if mu else float("nan")
        print(f"{label:<34}{mu:>13.5g}{sd:>13.3g}{pct:>9.1f}{v.min():>13.5g}{v.max():>13.5g}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/p1_transient_m1")
