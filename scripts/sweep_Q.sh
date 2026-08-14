#!/bin/bash
#
# Phase 1 flow-rate ladder (CLAUDE.md 10.2 item 1).
#
# 5 m3/h is the LD3007MS FREE-AIR rating. A 30 mm axial fan pushing through a
# 20 mm port against ~30 Pa of system loss will deliver well under that, and the
# answer changes QUALITATIVELY across the range -- Re_port goes 5830 -> 1450,
# i.e. turbulent -> laminar. So this is not padding; it is the study.
#
# Three cheap runs on one mesh. Report every metric as a function of Q.
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for Q in 5 2.5 1.25; do
    TAG=$(echo "$Q" | tr '.' 'p')
    NAME="p1_Q_${TAG}_m2"

    # Re_port = 1319 * U_in. Below ~2300 the flow is laminar and kOmegaSST is
    # not defensible -- pick the model from the physics, not from habit.
    MODEL=$(awk -v q="$Q" 'BEGIN{print (q/3600/3.14159265e-4*0.02/1.516e-5 < 2300) ? "laminar" : "kOmegaSST"}')

    echo "=== $NAME  (Q = $Q m3/h, $MODEL)"
    "$ROOT/scripts/generate_case.sh" --name "$NAME" --phase 1 --mesh m2 \
        --Q "$Q" --model "$MODEL"
    ( cd "$ROOT/runs/$NAME" && ./Allrun )
done

echo
echo "=== ladder complete. Compare:"
echo "  runs/p1_Q_*/postProcessing/trayPlane/0/*.dat      tray-level speed"
echo "  runs/p1_Q_*/postProcessing/ageMean/0/*.dat        ventilation effectiveness"
echo "  runs/p1_Q_*/postProcessing/traySlotFlux/0/*.dat   slot flow as %% of Q"
echo
echo "The headline is not any single run -- it is how the tray metrics vary"
echo "with Q, because Q itself is the largest open uncertainty."
