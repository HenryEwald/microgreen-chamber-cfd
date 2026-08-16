#!/bin/bash
#
# Run the whole Phase 1 transient analysis in one go.
#
#   validation/phase1_report.sh [runs/<case> ...]
#
# With no arguments it picks up every runs/p1_trans_* case. Writes figures into
# validation/ and prints the tables to stdout; redirect if you want them kept.
#
# This is orchestration only -- every number comes from the scripts it calls, so
# there is one implementation of each calculation, not two:
#
#   compare_transients.py   cross-case table + pairwise significance + figure
#   compare_transients.py --window-sweep
#                           is the mean still drifting at the 2.75-tau discard?
#   plot_transient.py       per-case time series, spectrum, flapping evidence
#   scripts/age_of_air.sh   mean age of air on the TIME-AVERAGED flux phiMean
#
# The age step needs `phiMean`, which fieldAverage only starts writing at
# timeStart (2.75 tau). A case that has not passed its averaging window is
# skipped with a note rather than failing the whole report.
#
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CASES=("$@")
if [ ${#CASES[@]} -eq 0 ]; then
    mapfile -t CASES < <(ls -d runs/p1_trans_* 2>/dev/null)
fi
[ ${#CASES[@]} -gt 0 ] || { echo "no runs/p1_trans_* cases found" >&2; exit 1; }

# Only cases that actually produced a tray signal are worth analysing.
USABLE=()
for c in "${CASES[@]}"; do
    if ls "$c"/postProcessing/traySignal/*/surfaceFieldValue.dat >/dev/null 2>&1; then
        USABLE+=("$c")
    else
        echo "skip $(basename "$c"): no traySignal output"
    fi
done
[ ${#USABLE[@]} -gt 0 ] || { echo "no case has traySignal output -- have the runs started?" >&2; exit 1; }

echo
echo "############################################################"
echo "# 1. CROSS-CASE COMPARISON"
echo "############################################################"
python3 validation/compare_transients.py "${USABLE[@]}"

echo
echo "############################################################"
echo "# 2. DISCARD-WINDOW SENSITIVITY"
echo "#    The mean must stop moving well before the 2.75-tau"
echo "#    discard. If it is still drifting there, the run has"
echo "#    not forgotten its initial field and the average is"
echo "#    contaminated however long the record is."
echo "############################################################"
python3 validation/compare_transients.py --window-sweep "${USABLE[@]}"

echo
echo "############################################################"
echo "# 2b. SPECTRUM -- where is the unsteadiness, and is the"
echo "#     peak even resolved? A peak sitting AT 1/T is the"
echo "#     window fundamental, not a measurement."
echo "############################################################"
python3 validation/compare_transients.py --spectrum "${USABLE[@]}"

echo
echo "############################################################"
echo "# 3. PER-CASE TRANSIENT STATISTICS"
echo "############################################################"
for c in "${USABLE[@]}"; do
    echo
    echo "--- $(basename "$c")"
    python3 validation/plot_transient.py "$c"
done

echo
echo "############################################################"
echo "# 4. MEAN AGE OF AIR, on the time-averaged flux"
echo "#    Check ageOutlet == tau FIRST -- if it does not, the"
echo "#    transport solve did not converge and ageMean/ageMax"
echo "#    are meaningless (validation/age_of_air.md)."
echo "############################################################"
for c in "${USABLE[@]}"; do
    echo
    echo "--- $(basename "$c")"
    if ! ls "$c"/[0-9]*/phiMean >/dev/null 2>&1; then
        echo "    no phiMean yet -- fieldAverage starts at 2.75 tau, and the case"
        echo "    must be reconstructed (Allrun does that when the solve ends)."
        continue
    fi
    scripts/age_of_air.sh "$c"
done

cat <<'EOF'

############################################################
# ACCEPTANCE -- CLAUDE.md 9. State these explicitly.
############################################################
  1. checkMesh passed                     grep '^Mesh OK' runs/<case>/log.checkMesh
  2. total volume == V_air 2.3296e-3      grep 'Total volume' runs/<case>/log.checkMesh
                                          (a sealed tray slot is invisible to
                                           every other mesh metric -- CLAUDE.md 7)
  3. mass balance closes                  postProcessing/inletFlux + outletFlux
  4. monitored quantities flat            section 1 above, RMS column
  5. averaging window adequate            section 1, N_eff column (>= 30 good,
                                          10-30 marginal, < 10 extend the run)
  6. discard window adequate              section 2 -- mean not still drifting
  7. age solve converged                  section 4 -- ageOutlet == tau

Carry the uncertainties, do not drop them:
  turbulence model  ~89 % on tray mean speed  <- the largest error bar
  age discretisation ~9 % (limitedLinear vs upwind)
  mesh (m0 vs m1)   ~0.3 % on tray mean, but UNTESTED for the transient
EOF
