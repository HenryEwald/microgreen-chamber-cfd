#!/bin/bash
#
# Phase 1 flow-rate ladder (CLAUDE.md 10.2 item 1).
#
# 5 m3/h is the LD3007MS FREE-AIR rating. A 30 mm axial fan pushing through a
# 20 mm port against ~30 Pa of system loss will deliver well under that, and the
# answer changes QUALITATIVELY across the range -- Re_port goes 5830 -> 1450,
# i.e. turbulent -> laminar. So this is not padding; it is the study.
#
# ---------------------------------------------------------------------------
# REWRITTEN 2026-08-15 -- the previous version was steady, on m2, and described
# itself as "three cheap runs". All three of those were wrong.
# ---------------------------------------------------------------------------
#   steady   The chamber flaps at BOTH ends of this ladder. Four steady runs
#            across a 16x resolution range never came within four orders of the
#            residualControl target (CLAUDE.md 5.1, 7). A steady sweep produces
#            three non-converged fields and a plot that looks fine.
#
#   m2       5.97 M cells; a time-accurate run there is ~100 h EACH.
#
#   "cheap"  A 6.6-tau transient is ~24.5 k steps at EVERY Q -- tau ~ 1/Q and
#            dt ~ 1/Q cancel exactly (CLAUDE.md 5.1, retraction of 2026-08-15).
#            Low Q is NOT the cheap end of this ladder. There is no cheap end.
#            Budget ~17 h per rung at m0+jetRefine on 8 ranks.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

MESH=${MESH:-m0}
QVALS=${QVALS:-"5 2.5 1.25"}
CPUSET=${FOAM_CPUSET:-0-7}

N=$(echo "$QVALS" | wc -w)
cat <<EOF
=== Phase 1 flow ladder
    mesh $MESH (+jetRefine)   Q values: $QVALS   ($N cases)

    ⚠ COST. ~24.5 k steps per case at ~2.5 s/step on 8 ranks => ~17 h EACH,
      i.e. >= $((N * 17)) h for this ladder. The step count is the SAME at every
      Q; the flow rate does not buy you a cheaper run.

    Override: QVALS="5 1.25" MESH=m0 ./scripts/sweep_Q.sh
EOF

for Q in $QVALS; do
    TAG=$(echo "$Q" | tr '.' 'p')

    # Re_port = 1319 * U_in. Below ~2300 the flow is laminar and kOmegaSST is
    # not defensible -- pick the model from the physics, not from habit. This
    # was measured, not assumed: at Q = 1.25 the RANS arm solves a 6x more
    # viscous chamber (nu_eff/nu = 6, Re_eff = 242) and over-predicts tray mean
    # speed by 89 % (CLAUDE.md 5.2).
    RE=$(awk -v q="$Q" 'BEGIN{printf "%.0f", q/3600/3.14159265e-4*0.02/1.516e-5}')
    MODEL=$(awk -v re="$RE" 'BEGIN{print (re < 2300) ? "laminar" : "kOmegaSST"}')
    NAME="p1_Q_${TAG}_${MESH}_${MODEL}"

    echo
    echo "=== $NAME  (Q = $Q m3/h, Re_port = $RE, $MODEL)"

    # The 2300 threshold is a clean split only at the ends of the ladder. In the
    # TRANSITIONAL band neither closure is defensible and CLAUDE.md 5.2 asks for
    # both arms and the spread reported as a modelling uncertainty -- this loop
    # picks one, so say plainly that one is not enough here.
    if awk -v re="$RE" 'BEGIN{exit !(re >= 2300 && re < 4000)}'; then
        echo "    !! Re_port = $RE is TRANSITIONAL (2300-4000). Neither laminar nor"
        echo "       a fully turbulent RANS closure is defensible at this rung."
        echo "       This loop runs $MODEL only. CLAUDE.md 5.2 asks for BOTH and"
        echo "       the spread reported as modelling uncertainty -- at Q = 1.25"
        echo "       that spread was measured at 89 % on tray mean speed, the"
        echo "       largest error bar in the project. Add the other arm with:"
        echo "         scripts/generate_case.sh --name ${NAME%_*}_laminar \\"
        echo "             --phase 1 --mesh $MESH --Q $Q --model laminar \\"
        echo "             --transient --jetRefine"
    fi

    [ -e "$ROOT/runs/$NAME" ] && { echo "    exists, skipping"; continue; }

    # --jetRefine only matters for the laminar arm -- the RANS arm's nut
    # thickens the shear layer by sqrt(6) and hides the under-resolution. But it
    # is applied to BOTH here on purpose: turning it on for only some rungs
    # would confound the Q comparison with a mesh change (CLAUDE.md 7).
    "$ROOT/scripts/generate_case.sh" --name "$NAME" --phase 1 --mesh "$MESH" \
        --Q "$Q" --model "$MODEL" --transient --jetRefine

    ( cd "$ROOT/runs/$NAME" && FOAM_CPUSET="$CPUSET" ./Allrun ) \
        || echo "!! $NAME did not complete -- see runs/$NAME/log.pimpleFoam"
done

cat <<'EOF'

=== ladder complete. Analyse as TIME AVERAGES, not single values:

    python3 validation/compare_transients.py runs/p1_Q_*
    scripts/age_of_air.sh runs/<case>       # ventilation effectiveness on phiMean

Note `age` is NOT a function object in a transient run -- it solves a steady
transport equation, so a snapshot of it on a flapping jet is meaningless
(CLAUDE.md 8.4). Mean age comes post-hoc from phiMean via the script above; the
old postProcessing/ageMean/ path does not exist for these cases.

The headline is not any single run -- it is how the tray metrics vary with Q,
because Q itself is the largest open uncertainty. Report each rung as mean +-
correlated-sample SE; a difference between rungs is only real if it clears it.
EOF
