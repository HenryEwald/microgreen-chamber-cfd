#!/usr/bin/env python3
"""Convergence + monitor plots for a Phase 1 case.

CLAUDE.md 8.2 and 9.5: `foamMonitor` is not in this build, and the acceptance
criteria say to PLOT the monitored quantities rather than eyeball the last line.
This is the tool that does that.

    python3 validation/plot_convergence.py runs/p1_baseline_m1

Writes validation/<case-id>_convergence.png.

Reads the function-object output under postProcessing/ plus the continuity
errors, which are only in the solver log. Deliberately stdlib + numpy +
matplotlib: CLAUDE.md 2 records no pandas and no pyvista on this machine.
"""

import re
import sys
import pathlib

import numpy as np
import matplotlib

matplotlib.use("Agg")  # no display on a headless solve box
import matplotlib.pyplot as plt

# --- palette ---------------------------------------------------------------
# Reference categorical palette, light mode, slots taken IN ORDER. Panels are
# independent small multiples, so each one starts again at slot 1.
#
# NOTE: the palette validator is a node script and there is no JS runtime on
# this machine, so it could not be run. These are the documented slots used
# unmodified and in documented order on the adjacent pairlist (lines), which is
# the case the reference instance records as passing every gate. Slots 3 and 4
# sit below 3:1 contrast on a light surface, so the relief rule applies: every
# series carrying them is DIRECT-LABELLED, not left to the legend alone.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8880"

# Acceptance thresholds, so the bar is drawn on the chart rather than asserted
# in prose. CLAUDE.md 9.2.
RESIDUAL_BAR = 1e-4  # "3-4 orders" from an initial residual of 1


def read_fo(path, ncols=1):
    """Read an OpenFOAM function-object .dat.

    Vector entries are written as `(x y z)`, which no plain loadtxt handles, so
    strip the parens and take the columns positionally.
    """
    times, vals = [], []
    for line in pathlib.Path(path).read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.replace("(", " ").replace(")", " ").split()
        times.append(float(parts[0]))
        vals.append([float(v) for v in parts[1 : 1 + ncols]])
    return np.array(times), np.array(vals)


def read_solver_info(path):
    """solverInfo.dat mixes solver-name strings into the numeric columns, so
    pick the initial-residual column for each field out of the header by name.
    """
    lines = pathlib.Path(path).read_text().splitlines()
    header = next(l for l in lines if l.startswith("# Time"))
    cols = header.lstrip("#").split()
    idx = {c: i for i, c in enumerate(cols)}

    times, series = [], {}
    wanted = [c for c in cols if c.endswith("_initial")]
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        times.append(float(parts[0]))
        for w in wanted:
            series.setdefault(w, []).append(float(parts[idx[w]]))
    return np.array(times), {k: np.array(v) for k, v in series.items()}


def read_continuity(log_path):
    """Continuity errors exist only in the solver log, one line per iteration."""
    pat = re.compile(
        r"sum local = ([0-9.eE+-]+), global = ([0-9.eE+-]+), "
        r"cumulative = ([0-9.eE+-]+)"
    )
    local, cumulative = [], []
    for line in pathlib.Path(log_path).read_text().splitlines():
        m = pat.search(line)
        if m:
            local.append(float(m.group(1)))
            cumulative.append(float(m.group(3)))
    n = np.arange(1, len(local) + 1)
    return n, np.array(local), np.array(cumulative)


def style(ax, title, ylabel, xlabel=None):
    """Recessive grid and axes; all text in ink tokens, never a series colour."""
    ax.set_title(title, color=INK, fontsize=10.5, loc="left", pad=8)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=9)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    ax.grid(True, color=INK_MUTED, alpha=0.18, linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_MUTED)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=INK_2, labelsize=8.5, length=3, width=0.8)
    ax.set_facecolor(SURFACE)


def label_end(ax, x, y, text, color, dy=0):
    """Direct label at the right end of a line -- the relief rule for the
    low-contrast slots, and it removes the legend round-trip generally.

    `dy` nudges the label in points where two series finish on top of each
    other (Ux and Uz do).
    """
    ax.annotate(
        text,
        xy=(x[-1], y[-1]),
        xytext=(4, dy),
        textcoords="offset points",
        color=color,
        fontsize=8.5,
        va="center",
        fontweight="medium",
    )


# CLAUDE.md 6.1 -- free air volume, the residence-time denominator.
V_AIR = 2.530e-3  # m3


def case_tau(case):
    """Residence time V_air / Q, from the case's own inlet BC.

    Authoritative because it is what the solver actually applied, rather than
    what a note says was intended. Returns None if the BC cannot be parsed, so
    the caller can omit the reference line instead of drawing a wrong one.
    """
    try:
        txt = (case / "0.orig/U").read_text()
    except OSError:
        return None
    m = re.search(r"^\s*volumetricFlowRate\s+([0-9.eE+-]+);", txt, re.M)
    if not m:
        return None
    q = float(m.group(1))
    return V_AIR / q if q else None


def main(case_dir):
    case = pathlib.Path(case_dir).resolve()
    pp = case / "postProcessing"
    out = pathlib.Path(__file__).parent / f"{case.name}_convergence.png"

    fig, axes = plt.subplots(3, 2, figsize=(13, 12))
    fig.patch.set_facecolor(SURFACE)
    ax = axes.ravel()

    # --- 1. pressure + velocity residuals ---------------------------------
    t, res = read_solver_info(pp / "residuals/0/solverInfo.dat")
    # Ux and Uz finish within a hair of each other, so stagger their labels.
    for slot, key, name, dy in [
        (0, "p_initial", "p", 0),
        (1, "Ux_initial", "Ux", 5),
        (2, "Uy_initial", "Uy", 0),
        (3, "Uz_initial", "Uz", -5),
    ]:
        ax[0].semilogy(t, res[key], color=SERIES[slot], linewidth=1.6, label=name)
        label_end(ax[0], t, res[key], name, SERIES[slot], dy)
    ax[0].axhline(RESIDUAL_BAR, color=INK_MUTED, linewidth=1.2, linestyle=(0, (5, 4)))
    # Annotate at the left edge -- mid-axis it lands on top of the Uy trace.
    ax[0].annotate(
        "CLAUDE.md 9.2 bar: 4 orders",
        xy=(t[0], RESIDUAL_BAR),
        xytext=(6, 5),
        textcoords="offset points",
        color=INK_2,
        fontsize=8,
    )
    style(ax[0], "Residuals -- pressure and velocity", "initial residual")

    # --- 2. turbulence residuals ------------------------------------------
    for slot, key, name in [(0, "k_initial", "k"), (1, "omega_initial", "omega")]:
        ax[1].semilogy(t, res[key], color=SERIES[slot], linewidth=1.6, label=name)
        label_end(ax[1], t, res[key], name, SERIES[slot])
    ax[1].axhline(RESIDUAL_BAR, color=INK_MUTED, linewidth=1.2, linestyle=(0, (5, 4)))
    style(ax[1], "Residuals -- turbulence", "initial residual")

    # --- 3. the metric surface (CLAUDE.md 9.5) ----------------------------
    tt, tray = read_fo(pp / "trayPlane/0/surfaceFieldValue.dat", ncols=4)
    magU = tray[:, 3]
    ax[2].plot(tt, magU, color=SERIES[0], linewidth=1.6)
    # Band over the last half of the run: the honest summary of an oscillating
    # signal is its range, not its final value.
    half = tt > tt[-1] / 2
    lo, hi, mean = magU[half].min(), magU[half].max(), magU[half].mean()
    ax[2].axhspan(lo, hi, color=SERIES[0], alpha=0.12, linewidth=0)
    ax[2].axhline(mean, color=SERIES[0], linewidth=1.0, linestyle=(0, (5, 4)))
    ax[2].annotate(
        f"2nd half: {mean:.3f} +/- {100 * (hi - lo) / 2 / mean:.1f}%",
        xy=(tt[len(tt) // 2], hi),
        xytext=(0, 6),
        textcoords="offset points",
        color=INK_2,
        fontsize=8.5,
    )
    style(ax[2], "Tray-plane mean speed  (z = 30 mm)", "|U|  [m/s]")

    # --- 4. tray uniformity ------------------------------------------------
    tc, cov = read_fo(pp / "trayUniformity/0/surfaceFieldValue.dat")
    ax[3].plot(tc, cov[:, 0], color=SERIES[0], linewidth=1.6)
    style(ax[3], "Tray-plane uniformity  (CoV of |U|, lower = more uniform)", "CoV  [-]")

    # --- 5. age of air -----------------------------------------------------
    ta, amean = read_fo(pp / "ageMean/0/volFieldValue.dat")
    _, amax = read_fo(pp / "ageMax/0/volFieldValue.dat")
    for slot, (x, y, name) in enumerate(
        [(ta, amean[:, 0], "mean"), (ta, amax[:, 0], "max")]
    ):
        ax[4].plot(x, y, color=SERIES[slot], linewidth=1.6, marker="o", markersize=4.5)
        label_end(ax[4], x, y, name, SERIES[slot])
    # tau = V_air / Q -- the sanity target the FO header names.
    #
    # Read from the case's own inlet BC, NOT hard-coded. The 1.82 s that used to
    # be written here is correct only at Q = 5 m3/h; tau scales as 1/Q, so at the
    # Q = 1.25 m3/h working value (CLAUDE.md 10.2) the true figure is 7.29 s and
    # this reference line was 4x too low -- which would make a badly ventilated
    # chamber look four times worse than it is. Same bug, same fix, as
    # plot_transient.py (2026-08-15).
    tau_s = case_tau(case)
    if tau_s:
        ax[4].axhline(tau_s, color=INK_MUTED, linewidth=1.2, linestyle=(0, (5, 4)))
        ax[4].annotate(
            f"nominal tau = {tau_s:.2f} s",
            xy=(ta[0], tau_s),
            xytext=(0, 5),
            textcoords="offset points",
            color=INK_2,
            fontsize=8,
        )
    ax[4].set_ylim(bottom=0)
    style(ax[4], "Age of air  (ventilation effectiveness)", "age  [s]", "iteration")

    # --- 6. continuity (CLAUDE.md 9.3) ------------------------------------
    n, local, cumulative = read_continuity(case / "log.simpleFoam")
    for slot, (y, name) in enumerate(
        [(local, "sum local"), (np.abs(cumulative), "|cumulative|")]
    ):
        ax[5].semilogy(n, y, color=SERIES[slot], linewidth=1.3)
        label_end(ax[5], n, y, name, SERIES[slot])
    style(ax[5], "Continuity error  (must be small AND not growing)", "error  [-]", "iteration")

    for a in ax:
        a.set_xlim(left=0)
    ax[0].set_xlabel("iteration", color=INK_2, fontsize=9)
    ax[1].set_xlabel("iteration", color=INK_2, fontsize=9)

    fig.suptitle(
        f"{case.name} -- Phase 1 convergence and monitors",
        color=INK,
        fontsize=13,
        x=0.055,
        ha="left",
        y=0.985,
    )
    fig.text(
        0.055,
        0.958,
        "Q = 5 m3/h (FREE-AIR upper bound, not the operating point -- CLAUDE.md 6.2)",
        color=INK_2,
        fontsize=9.5,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(f"wrote {out}")

    # Table view: the chart's numbers in text, per the accessibility pass.
    print(f"\n{'quantity':<28}{'2nd-half mean':>15}{'min':>14}{'max':>14}{'+/- %':>9}")
    for name, x, y in [
        ("tray mean speed [m/s]", tt, magU),
        ("tray CoV [-]", tc, cov[:, 0]),
        ("age mean [s]", ta, amean[:, 0]),
        ("age max [s]", ta, amax[:, 0]),
    ]:
        h = x > x[-1] / 2
        m, a, b = y[h].mean(), y[h].min(), y[h].max()
        print(f"{name:<28}{m:>15.4f}{a:>14.4f}{b:>14.4f}{100 * (b - a) / 2 / m:>9.1f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "runs/p1_baseline_m1")
