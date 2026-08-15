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
# ---------------------------------------------------------------------------
# REWRITTEN 2026-08-15. The previous version would have produced nothing usable.
# ---------------------------------------------------------------------------
# It ran `--phase 2 --mesh m2` with the default kOmegaSST and NO --transient.
# Every one of those three is now known to be wrong for this chamber:
#
#   steady      The flow does not converge at ANY Q tested -- four steady runs
#               across a 16x resolution range, none within four orders of the
#               residualControl target (CLAUDE.md 5.1, 7). Phase 2 is WORSE, not
#               better: 6.3's stable stratification is a second, independent
#               reason to expect it to stall. The sweep would have spent days
#               producing non-converged fields and reported them as results.
#
#   m2          5.97 M cells. A time-accurate run there is ~100 h EACH
#               (CLAUDE.md 5.1). Transient work is m0/m1 only.
#
#   kOmegaSST   At Q = 1.25 m3/h, Re_port = 1458 is laminar, and the RANS arm
#               was measured solving a 6x more viscous chamber -- nu_eff/nu = 6,
#               Re_eff = 242 -- which damps the very physics the sweep is
#               measuring (CLAUDE.md 5.2).
#
# It also never passed --led, so it silently used the 38.4 W default, which at
# Q = 1.25 m3/h is a 112 C chamber (CLAUDE.md 6.3). That is now an explicit
# choice below rather than an accident.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

MESH=${MESH:-m0}
Q=${Q:-1.25}
LED=${LED:-38.4}
MODEL=${MODEL:-laminar}
CPUSET=${FOAM_CPUSET:-0-7}

# TBD -- confirm the target regimes (CLAUDE.md 10.4 item 7). Placeholder set:
#   0     free fall / orbit
#   1.62  Lunar
#   3.72  Mars
#   9.81  Earth (baseline)
GVALS=${GVALS:-"0 1.62 3.72 9.81"}

# --- cost, up front --------------------------------------------------------
# A 6.6-tau transient is ~24.5 k steps at m0+jetRefine REGARDLESS of Q (dt and
# endTime both scale as 1/Q and cancel -- CLAUDE.md 5.1). Phase 1 laminar
# measured 2.53 s/step on 8 ranks; buoyantPimpleFoam carries an extra energy
# equation and a stiffer pressure problem, so budget appreciably more.
N=$(echo "$GVALS" | wc -w)
cat <<EOF
=== Phase 3 gravity sweep
    mesh $MESH   Q $Q m3/h   model $MODEL   LED $LED W
    g values: $GVALS  ($N cases + 1 cross-check)

    ⚠ COST. Each case is a ~24.5 k-step transient (the step count is the same
      at every Q -- dt and endTime both scale as 1/Q and cancel).

      MEASURED 2026-08-15 on runs/p2_smoke_m0: buoyantPimpleFoam is ~2.9x the
      per-step cost of pimpleFoam on the same mesh. Phase 1 isothermal runs at
      2.53 s/step on 8 clean ranks, so buoyant is ~7.3 s/step:

          ~50 h PER CASE  ->  ~$((N * 50)) h for this sweep, i.e. ~$(( (N * 50 + 12) / 24 )) DAYS.

      That per-step figure is extrapolated across contention levels -- take one
      clean measurement of a few hundred steps before trusting it.

      STRONGLY consider trimming to the two endpoints first:

          GVALS="0 9.81" ./scripts/sweep_gravity.sh

      If 0 g and 1 g are indistinguishable within their correlated-sample error
      bars, there is no Ri crossover to resolve and the intermediate Lunar/Mars
      points are not worth the machine time. That is a ~4 day question instead
      of a ~10 day one, and it is the question the study actually asks.

    Override with environment variables, e.g.:
        GVALS="0 9.81" MESH=m0 ./scripts/sweep_gravity.sh
EOF

for G in $GVALS; do
    TAG=$(printf "%.3f" "$G" | tr '.' 'p')
    NAME="p3_g_${TAG}_${MESH}"

    echo
    echo "=== $NAME  (g = $G m/s2)"
    [ -e "$ROOT/runs/$NAME" ] && { echo "    exists, skipping"; continue; }

    # --transient: the flow does not settle at 1 g and stable stratification
    # makes that more likely under buoyancy, not less.
    # --jetRefine: the laminar shear layer is otherwise unresolved anywhere in
    # an m0 domain (x_res 202 mm > the 186.7 mm path).
    "$ROOT/scripts/generate_case.sh" --name "$NAME" --phase 2 --mesh "$MESH" \
        --Q "$Q" --led "$LED" --model "$MODEL" --transient --jetRefine --g "$G"

    ( cd "$ROOT/runs/$NAME" && FOAM_CPUSET="$CPUSET" ./Allrun ) || {
        echo "!! $NAME did not complete."
        echo "!! High-Ri cases are stiffer. Check whether the PIMPLE outer loop"
        echo "!! is contracting before touching anything else -- fvSolution"
        echo "!! documents the nOuterCorrectors/residualControl failure mode."
        echo "!! Do NOT relax your way out of it (CLAUDE.md 5.2)."
    }
done

# At exactly g = 0 buoyancy vanishes and the flow is purely fan-driven forced
# convection. pimpleFoam is then cheaper and better conditioned -- run it as the
# 0 g endpoint and cross-check against the buoyantPimpleFoam result above. The
# two should agree; if they do not, the buoyant solver setup is suspect, and
# this is the cheapest place to find that out.
echo
echo "=== 0 g cross-check with the incompressible solver"
if [ -e "$ROOT/runs/p3_g_0p000_${MESH}_iso" ]; then
    echo "    exists, skipping"
else
    "$ROOT/scripts/generate_case.sh" --name "p3_g_0p000_${MESH}_iso" --phase 1 \
        --mesh "$MESH" --Q "$Q" --model "$MODEL" --transient --jetRefine
    ( cd "$ROOT/runs/p3_g_0p000_${MESH}_iso" && FOAM_CPUSET="$CPUSET" ./Allrun )
fi

cat <<'EOF'

=== sweep complete.

Analyse with the transient tooling, NOT by reading a single final value -- every
case here is unsteady by construction:

    python3 validation/compare_transients.py runs/p3_g_*
    scripts/age_of_air.sh runs/<case>          # ventilation effectiveness

The headline plot of the whole study is tray-level ventilation vs Ri, NOT vs g.
The interesting physics is the crossover. State the reference velocity scale on
the axis (U_bulk), and report the mean with its correlated-sample error bar --
a difference between two g values is only real if it clears that bar.

⚠ Absolute temperatures in these runs are not a prediction of the built chamber:
at Q = 1.25 m3/h the LED default of 38.4 W implies a ~112 C chamber (CLAUDE.md
6.3). Flow structure and stratification are the usable output.
EOF
