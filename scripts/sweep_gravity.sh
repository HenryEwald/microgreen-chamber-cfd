#!/bin/bash
#
# Phase 3 gravity sweep (CLAUDE.md 5.2, 8.3).
#
# The knob is ONE FILE: constant/g. Mesh, turbulence model and BCs stay frozen
# across the sweep or the result is not interpretable.
#
# IMPORTANT -- read CLAUDE.md 6.3 before interpreting anything this produces.
# The LED is on the CEILING, so this chamber is STABLY stratified: buoyancy
# SUPPRESSES vertical mixing rather than driving it. The expected result may run
# backwards from intuition -- higher g => stronger stratification => WORSE
# tray-level exchange, with g = 0 potentially the best-mixed case in the sweep.
#
# Report against Richardson number, not raw g, and state the reference velocity
# scale explicitly: U_in and U_bulk differ by 40x, which moves Ri by ~1600x.
# U_bulk is the honest choice -- it describes the region gravity actually changes.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# TBD -- confirm the target regimes (CLAUDE.md 10.4 item 7). Placeholder set:
#   0     free fall / orbit
#   1.62  Lunar
#   3.72  Mars
#   9.81  Earth (baseline)
for G in 0 1.62 3.72 9.81; do
    TAG=$(printf "%.3f" "$G" | tr '.' 'p')
    NAME="p3_g_${TAG}_m2"

    echo "=== $NAME  (g = $G m/s2)"
    "$ROOT/scripts/generate_case.sh" --name "$NAME" --phase 2 --mesh m2 --g "$G"
    ( cd "$ROOT/runs/$NAME" && ./Allrun ) || {
        echo "!! $NAME did not complete."
        echo "!! High-Ri cases are stiffer and may need buoyantPimpleFoam."
        echo "!! Do NOT force simpleFoam-style relaxation onto a case that has"
        echo "!! gone unsteady (CLAUDE.md 5.2). Investigate before continuing."
    }
done

# At exactly g = 0 buoyancy vanishes and the flow is purely fan-driven forced
# convection. simpleFoam is then cheaper and better conditioned -- run it as the
# 0 g endpoint and cross-check against the buoyantSimpleFoam result above.
echo "=== 0 g cross-check with simpleFoam"
"$ROOT/scripts/generate_case.sh" --name p3_g_0p000_m2_simple --phase 1 --mesh m2
( cd "$ROOT/runs/p3_g_0p000_m2_simple" && ./Allrun )

echo
echo "=== sweep complete. The headline plot of the whole study is tray-level"
echo "    ventilation vs Ri, NOT vs g. The interesting physics is the crossover."
