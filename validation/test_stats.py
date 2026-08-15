#!/usr/bin/env python3
"""Regression test for the correlated-sample statistics in compare_transients.py.

    python3 validation/test_stats.py

The error bar on a time-averaged tray metric is what decides whether a mesh or
model difference is real (CLAUDE.md 9.6). If it is wrong, every comparison built
on it is wrong in a way no amount of CFD will reveal -- so it is tested against
signals whose answer is known analytically, and against the naive estimator it
replaces.

The last test is the one that matters: for a correlated signal, sd/sqrt(N)
covers the true mean 15 % of the time where it should cover it 95 %. That is not
a small correction, it is the difference between "the mesh is the limiting
error" and "we cannot tell".
"""

import sys
import pathlib
import importlib.util

import numpy as np

HERE = pathlib.Path(__file__).parent
_spec = importlib.util.spec_from_file_location("ct", HERE / "compare_transients.py")
ct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ct)

DT = 1e-3
FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not cond:
        FAILED.append(name)


def ar1(n, a, seed):
    """AR(1): x[i] = a*x[i-1] + white. Correlation time -dt/ln(a)."""
    r = np.random.default_rng(seed)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = a * x[i - 1] + r.standard_normal()
    return x


print("integral timescale / effective sample size")

# Independent samples must not be penalised: N_eff == N.
w = np.random.default_rng(7).standard_normal(20000)
_, ne = ct.integral_timescale(w, DT)
check("white noise gives N_eff == N", abs(ne / 20000 - 1) < 0.05, f"ratio {ne / 20000:.3f}")

# Correlated samples must be, and by roughly the right factor. Truncating the
# autocorrelation at its first zero biases T_int low, so accept 0.6-1.2x theory.
x = ar1(20000, 0.99, 7)
t_int, ne = ct.integral_timescale(x, DT)
theory = -DT / np.log(0.99)
check("AR(1) T_int within 0.6-1.2x of theory",
      0.6 * theory < t_int < 1.2 * theory, f"{t_int:.5f} vs {theory:.5f} s")
check("AR(1) N_eff << N", ne < 20000 / 50, f"N_eff {ne:.0f} of 20000")

# A pure tone: the autocorrelation is a cosine, so its integral to the first
# zero is 1/(2*pi*f).
t = np.arange(20000) * DT
y = np.sin(2 * np.pi * 1.0 * t) + 0.1 * np.random.default_rng(3).standard_normal(20000)
t_int, _ = ct.integral_timescale(y, DT)
check("1 Hz tone T_int ~ 1/(2 pi f)", abs(t_int - 1 / (2 * np.pi)) < 0.02,
      f"{t_int:.4f} vs {1 / (2 * np.pi):.4f} s")

# Degenerate input must not raise.
_, ne = ct.integral_timescale(np.ones(500), DT)
check("constant signal does not raise", True)
check("too-short signal returns nan", not np.isfinite(ct.integral_timescale(np.zeros(4), DT)[0]))

print("\ncoverage of the true mean by +-2 SE  (target ~95 %)")
TRIALS, N = 300, 4000
aware = naive = 0
for k in range(TRIALS):
    z = ar1(N, 0.98, k)          # true mean is 0
    s = ct.stats(np.arange(N) * DT, z)
    aware += abs(s["mean"]) < 2 * s["se"]
    naive += abs(z.mean()) < 2 * z.std(ddof=1) / np.sqrt(N)
print(f"  correlation-aware  {100 * aware / TRIALS:.0f} %")
print(f"  naive sd/sqrt(N)   {100 * naive / TRIALS:.0f} %   <- the estimator NOT used, for contrast")
check("correlation-aware coverage is 85-99 %", 85 <= 100 * aware / TRIALS <= 99)
check("naive estimator is demonstrably too optimistic", 100 * naive / TRIALS < 60)

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {', '.join(FAILED)}")
    sys.exit(1)
print("all passed")
