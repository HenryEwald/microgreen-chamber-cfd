#!/bin/bash
#
# Mean age of air on the TIME-AVERAGED flow of a finished transient run.
#
#   scripts/age_of_air.sh runs/<case> [--field phi|phiMean] [--time T]
#
# Mean age of air is THE ventilation-effectiveness metric for this chamber
# (CLAUDE.md 8.4): the volume mean should land near tau = V_air/Q, and anything
# far above it is dead volume. The hood -- 0.72 L sitting entirely above the jet
# -- is expected to be the worst region by a wide margin, and this is how that
# gets demonstrated rather than asserted.
#
# ---------------------------------------------------------------------------
# Why this script exists: the CLAUDE.md 8.4 recipe does not work
# ---------------------------------------------------------------------------
# That recipe was:
#
#     cp <T>/phiMean <T>/phi
#     postProcess -func age -time <T>
#
# It fails, verified 2026-08-15, in two separate ways:
#
#   1. `-func age` cannot find a config -- there is no `age` file shipped under
#      etc/caseDicts/postProcessing, so the utility reports "Cannot find
#      functionObject file age" and exits 0 having done nothing. Silent.
#
#   2. More fundamentally, `age` CANNOT run under postProcess at all.
#      src/functionObjects/field/age/age.C line 128, inside read():
#
#          const auto& phi = mesh_.lookupObject<surfaceScalarField>(phiName_);
#
#      i.e. phi must already be REGISTERED when the function object is
#      CONSTRUCTED. postProcess constructs its function objects before it reads
#      any fields, and never auto-loads surfaceScalarFields anyway, so the
#      lookup fails at construction:
#
#          failed lookup of phi (objectRegistry region0)
#          available objects of type surfaceScalarField: 0()
#
#      Passing `-fields '(phi U)'` does not help -- that loads fields at execute
#      time, which is strictly after construction. `simpleFoam -postProcess`
#      does not help either, for the same reason.
#
# So `age` has to run INSIDE a solver, where createFields has registered phi and
# the turbulence model. It demonstrably works there -- the in-solver ageMean
# series is what every steady run in runs/ already has.
#
# The approach here: put the averaged flux in place as `phi`, then run the
# solver for ONE deliberately tiny time step (1e-8 s, adjustTimeStep off) so the
# function object fires on a flux field that is, to eight significant figures,
# exactly phiMean. Nothing is integrated; the step exists only to give `age` a
# live registry to attach to.
#
# Everything happens in a COPY under <case>/ageEval/, so the source case is
# never modified (CLAUDE.md 1.3: never hand-edit a generated case).
#
set -euo pipefail

CASE="" ; FIELD=phiMean ; TIME=""
while [ $# -gt 0 ]; do
    case "$1" in
        --field) FIELD=$2 ; shift 2 ;;
        --time)  TIME=$2  ; shift 2 ;;
        *)       CASE=$1  ; shift 1 ;;
    esac
done
[ -n "$CASE" ] || { echo "usage: $0 runs/<case> [--field phi|phiMean] [--time T]" >&2; exit 1; }
CASE="$(cd "$CASE" && pwd)"

# etc/bashrc is not written for `set -eu` -- see scripts/generate_case.sh.
set +eu
# shellcheck disable=SC1091
. /usr/lib/openfoam/openfoam2606/etc/bashrc
set -eu

cd "$CASE"

# Latest numeric time directory, unless one was named. `0.orig` is excluded by
# requiring the name to parse as a number.
if [ -z "$TIME" ]; then
    TIME=$(for d in [0-9]*; do
               [ -d "$d" ] || continue
               case "$d" in *[!0-9.]*) continue ;; esac
               echo "$d"
           done | sort -g | tail -1)
fi

if [ -z "$TIME" ] || [ ! -d "$TIME" ]; then
    # A parallel run keeps its fields in processor*/ until reconstructPar has
    # run. Allrun does that automatically at the end of a pimpleFoam solve, so
    # the usual cause of landing here is asking for the age of a run that has
    # not finished yet.
    if ls -d processor0/[0-9]* >/dev/null 2>&1; then
        echo "!! $CASE has no reconstructed time directory, but processor0/ has:" >&2
        ls -d processor0/[0-9]* | xargs -n1 basename | tr '\n' ' ' >&2; echo >&2
        echo "   This case is still decomposed. Either wait for the run to" >&2
        echo "   finish (Allrun reconstructs automatically) or run:" >&2
        echo "       cd $CASE && reconstructPar -latestTime" >&2
    else
        echo "no time directory in $CASE" >&2
    fi
    exit 1
fi

if [ ! -f "$TIME/$FIELD" ]; then
    echo "!! $TIME/$FIELD does not exist." >&2
    if [ "$FIELD" = phiMean ]; then
        echo "   phiMean is written by the fieldAverage function object in" >&2
        echo "   system/functions/transientMonitors, and only from timeStart" >&2
        echo "   onwards. Has this run passed its averaging window?" >&2
        echo "   To use an instantaneous snapshot instead: --field phi" >&2
        echo "   (but read the CLAUDE.md 8.4 note first -- a snapshot age on a" >&2
        echo "    flapping jet is not the mean age of air)" >&2
    fi
    exit 1
fi

WORK="$CASE/ageEval"
rm -rf "$WORK"
mkdir -p "$WORK/$TIME"

# Copy only what a single step needs: the mesh, the dicts, and one time.
cp -r constant "$WORK/"
cp -r system   "$WORK/"
cp "$TIME"/* "$WORK/$TIME/" 2>/dev/null || true
rm -f "$WORK/$TIME"/*Mean "$WORK/$TIME"/*Prime2Mean
cp "$TIME/$FIELD" "$WORK/$TIME/phi"

cd "$WORK"

# uniform/ carries time bookkeeping that would otherwise override startTime.
rm -rf "$TIME/uniform"

APP=$(foamDictionary -entry application -value system/controlDict)

# One step, sized by what the solver's "time" actually means.
#
#   steady   (simpleFoam / buoyantSimpleFoam)  -- "time" is an ITERATION COUNT,
#            so the step is 1. A single SIMPLE iteration barely moves the field
#            and the age FO fires after it.
#   transient(pimpleFoam / buoyantPimpleFoam)  -- time is seconds, so the step
#            is 1e-8 s: small enough that phi is still phiMean to eight figures.
case "$APP" in
    simpleFoam|buoyantSimpleFoam) DT=1 ;;
    *)                            DT=1e-8 ;;
esac

# %.16g, NOT %.10g. At t = 4000 a 1e-8 increment needs 12 significant digits to
# survive; %.10g printed it straight back as "4000", endTime then equalled
# startTime, the time loop ran ZERO iterations and the run reported a cheerful
# "End" having computed nothing. Verified 2026-08-15 -- that is the failure this
# format string exists to prevent.
END=$(awk -v t="$TIME" -v d="$DT" 'BEGIN{printf "%.16g", t + d}')
if [ "$END" = "$TIME" ]; then
    echo "!! endTime ($END) is not distinguishable from startTime ($TIME)." >&2
    echo "   The time loop would run zero iterations. Use an earlier time." >&2
    exit 1
fi
cat > system/controlDict <<EOF
FoamFile
{
    version 2.0; format ascii; class dictionary; object controlDict;
}
application     $APP;
startFrom       startTime;
startTime       $TIME;
stopAt          endTime;
endTime         $END;
deltaT          $DT;
adjustTimeStep  no;
writeControl    timeStep;
writeInterval   1;
writeFormat     binary;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   12;
runTimeModifiable false;
functions
{
    #include "functions/age"
}
EOF

# The time step is SCAFFOLDING -- it exists only so the age function object has
# a live registry with phi in it, and its momentum/pressure result is thrown
# away. So do not pay for a converged one: drop the PIMPLE outer loop to a
# single pass. Measured at 415 k cells this is the difference between ~11 outer
# correctors (22 GAMG pressure solves) and one, for a step that advances the
# clock by 1e-8 s and cannot change phi meaningfully at any setting.
#
# Only touches the ageEval COPY, never the source case. Harmless on a steady
# case, where the entry simply is not read.
if [ -f system/fvSolution ] && grep -q "nOuterCorrectors" system/fvSolution; then
    sed -i 's/^\( *nOuterCorrectors *\)[0-9][0-9]*;/\11;/' system/fvSolution
fi

echo "== mean age of air on $FIELD at t = $TIME  (case $(basename "$CASE"))"
# Still SERIAL, and the age solve itself is the remaining cost: nCorr 5, each
# pass capped at 1000 linear iterations because limitedLinear's solution-
# dependent limiter stops the outer residual contracting (see
# validation/age_of_air.md -- the caps are cosmetic, the identity confirms the
# answer). Expect several minutes on an m0 case, longer if the machine is busy.
# It is not hung; watch log.age.
echo "   (serial -- expect several minutes. Progress: $WORK/log.age)"
"$APP" > log.age 2>&1 || { echo "!! $APP failed -- see $WORK/log.age" >&2; tail -20 log.age >&2; exit 1; }

if ! grep -q "^End" log.age; then
    echo "!! $APP did not finish -- see $WORK/log.age" >&2; tail -20 log.age >&2; exit 1
fi
if grep -q "failed lookup of phi" log.age; then
    echo "!! phi was not registered -- the age FO cannot have run" >&2; exit 1
fi
# A zero-iteration run prints "Starting time loop" then "End" and looks like a
# success. Check the loop actually turned over.
if ! grep -qE "^(Time = |Iteration = )" log.age; then
    echo "!! the time loop ran ZERO iterations -- nothing was computed." >&2
    echo "   endTime $END vs startTime $TIME, deltaT $DT. See $WORK/log.age" >&2
    exit 1
fi

MEAN=$(grep -h -v '^#' postProcessing/ageMean/*/volFieldValue.dat 2>/dev/null | tail -1 | awk '{print $2}')
MAX=$(grep  -h -v '^#' postProcessing/ageMax/*/volFieldValue.dat  2>/dev/null | tail -1 | awk '{print $2}')
[ -n "$MEAN" ] || { echo "!! no ageMean output -- see $WORK/log.age" >&2; exit 1; }

# tau from the case's own inlet BC, not from a note.
Q=$(awk '/volumetricFlowRate/{gsub(";","",$2); print $2; exit}' 0.orig/U 2>/dev/null || true)
if [ -n "$Q" ]; then
    TAU=$(awk -v q="$Q" 'BEGIN{printf "%.2f", 2.530e-3/q}')
    echo "   tau (V_air/Q)      ${TAU} s"
    echo "   age, volume mean   ${MEAN} s   = $(awk -v a="$MEAN" -v t="$TAU" 'BEGIN{printf "%.2f", a/t}') tau"
    echo "   age, max           ${MAX} s   = $(awk -v a="$MAX" -v t="$TAU" 'BEGIN{printf "%.2f", a/t}') tau"
    echo
    echo "   A volume mean near 1 tau is a well-mixed chamber. Well above it means"
    echo "   dead volume -- expect the hood (CLAUDE.md 6.1) to carry most of it."
else
    echo "   age, volume mean   ${MEAN} s"
    echo "   age, max           ${MAX} s"
fi
echo "   age field written to $WORK/$END/age  (open in ParaView to locate the dead zones)"
