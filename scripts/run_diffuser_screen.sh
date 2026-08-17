#!/bin/bash
#
# Run the inlet-diffuser concept screen (doc/diffuser/design.md 3a).
#
#   control        no diffuser
#   cascade 30 deg 5 horizontal turning vanes
#   radial 15 deg  12 swirl vanes, S = 0.19  (attached)
#   radial 40 deg  12 swirl vanes, S = 0.60  (at the breakdown threshold)
#
# SEQUENTIAL, deliberately. OpenFOAM is memory-bandwidth bound (CLAUDE.md 3.2),
# so two concurrent cases contend even on disjoint core groups, and CCD1 has
# 32 MB of L3 against CCD0's 96 MB -- a paired run is not 2x, and it makes the
# per-case timings incomparable, which matters when the whole point is an A/B.
# To pair anyway:  FOAM_CPUSET=0-7 ./Allrun &  FOAM_CPUSET=8-15 ./Allrun &
#
# The meshes are already built and logged, so runApplication skips blockMesh /
# snappyHexMesh / checkMesh and this goes straight to renumberMesh + solve.
#
# Usage:  scripts/run_diffuser_screen.sh [case ...]      (default: all four)
#
set -uo pipefail          # NOT -e: a failed case must not kill the queue

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CASES=("$@")
[ ${#CASES[@]} -eq 0 ] && CASES=(p1d_ctrl_m0 p1d_casc30_m0 p1d_rad15_m0 p1d_rad40_m0)

# ~7.6 GB/case at 500 k cells x 60 retained write times (purgeWrite 0 since
# 2026-08-16), plus the same again in processor*/ until the post-run cleanup
# below frees it -- so budget ~10 GB/case. This was 2 GB/case when cases kept 5
# frames; leaving it there would have waved through a queue that needs 5x the
# disk. Refuse to start a 10 h queue that will die full at hour 7.
FREE_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
NEED_GB=$(( ${#CASES[@]} * 10 ))
if [ "$FREE_GB" -lt "$((NEED_GB + 5))" ]; then
    echo "!! only ${FREE_GB} GB free, want >= $((NEED_GB + 5)) GB for ${#CASES[@]} cases"
    exit 1
fi

STAMP=$(date +%Y%m%d-%H%M%S)
SUMMARY="$ROOT/validation/diffuser_screen_${STAMP}.log"
echo "diffuser screen started $(date -Is)"          | tee "$SUMMARY"
echo "cases: ${CASES[*]}"                           | tee -a "$SUMMARY"
echo "free disk: ${FREE_GB} GB"                     | tee -a "$SUMMARY"
echo                                                | tee -a "$SUMMARY"

FAILED=0
for c in "${CASES[@]}"; do
    d="$ROOT/runs/$c"
    if [ ! -x "$d/Allrun" ]; then
        echo "SKIP  $c -- no Allrun"                | tee -a "$SUMMARY"
        FAILED=$((FAILED + 1)); continue
    fi

    t0=$(date +%s)
    echo "== $c  started $(date -Is)"               | tee -a "$SUMMARY"
    ( cd "$d" && ./Allrun ) > "$d/allrun.out" 2>&1
    rc=$?
    t1=$(date +%s)
    hrs=$(awk -v s=$((t1 - t0)) 'BEGIN{printf "%.2f", s/3600}')

    # Exit status alone is not enough. Allrun returns 0 after printing its
    # acceptance checklist even when reconstructPar produced nothing -- the
    # 2026-08-15 failure where a finished run left only 0/ reconstructed while
    # processor*/ held 46 times, and nothing said so until post-processing went
    # looking. Assert a real time directory exists.
    ntimes=$(find "$d" -maxdepth 1 -regex '.*/[0-9][0-9.]*' \
             ! -name 0 ! -name 0.orig -printf . 2>/dev/null | wc -c)
    if [ "$rc" -eq 0 ] && [ "$ntimes" -gt 0 ]; then
        echo "   OK    ${hrs} h, ${ntimes} reconstructed time(s)" | tee -a "$SUMMARY"

        # Free processor*/ once the reconstruction is verified COMPLETE. With
        # purgeWrite 0 the decomposed copy is the same size as the reconstructed
        # one, so keeping both doubles a ~7.6 GB case for no benefit -- nothing
        # downstream reads processor*/ (age_of_air.sh only stats it to produce a
        # better error message when a case is NOT reconstructed).
        #
        # Guarded on the FRAME COUNT, not merely on "a time exists". Deleting
        # the decomposed data is irreversible, and a partial reconstruction that
        # left one time directory would otherwise look like success -- the same
        # class of failure as the bare `reconstructPar` that reconstructed
        # nothing and exited 0 (CLAUDE.md 10.3).
        want=$(awk -v e="$(grep -oP '^endTime\s+\K[0-9.eE+-]+' "$d/system/controlDict")" \
                   -v w="$(grep -oP '^writeInterval\s+\K[0-9.eE+-]+' "$d/system/controlDict")" \
               'BEGIN{printf "%d", e/w}')
        if [ "$want" -gt 0 ] && [ "$ntimes" -ge $((want * 9 / 10)) ]; then
            freed=$(du -sm "$d"/processor* 2>/dev/null | awk '{s+=$1} END{print s+0}')
            rm -rf "$d"/processor*
            echo "         reconstruction complete ($ntimes of ~$want frames);" \
                 "freed ${freed} MB of processor*/" | tee -a "$SUMMARY"
        else
            echo "         KEEPING processor*/ -- only $ntimes of ~$want frames" \
                 "reconstructed" | tee -a "$SUMMARY"
        fi
    else
        echo "   FAIL  rc=$rc, ${hrs} h, ${ntimes} time(s) -- see $d/allrun.out" \
            | tee -a "$SUMMARY"
        tail -20 "$d/allrun.out" | sed 's/^/         /' | tee -a "$SUMMARY"
        FAILED=$((FAILED + 1))
    fi
done

echo                                                | tee -a "$SUMMARY"
echo "finished $(date -Is), $FAILED failure(s)"     | tee -a "$SUMMARY"
echo                                                | tee -a "$SUMMARY"
echo "NEXT -- none of this is a result until CLAUDE.md 9 is checked per case:" | tee -a "$SUMMARY"
echo "  total volume vs V_air in log.checkMesh (already verified at mesh time)" | tee -a "$SUMMARY"
echo "  inlet + outlet flux ~ 0    postProcessing/inletFlux, outletFlux"        | tee -a "$SUMMARY"
echo "  tray metrics flat          postProcessing/trayPlane"                    | tee -a "$SUMMARY"
echo "  age of air                 scripts/age_of_air.sh runs/<case>"           | tee -a "$SUMMARY"
exit $FAILED
