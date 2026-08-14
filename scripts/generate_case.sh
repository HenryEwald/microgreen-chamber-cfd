#!/bin/bash
#
# Generate a run case from templates/ (CLAUDE.md 1.3, 8.3).
#
# Cases in runs/ are DISPOSABLE. Any result must be reproducible from this
# script plus a parameter set -- so never hand-edit a generated case, change
# the parameters or the template and regenerate.
#
# Usage:
#   scripts/generate_case.sh --name p1_baseline_m2 [options]
#
# Options:
#   --name    NAME    run directory under runs/     (required)
#   --phase   1|2     1 = simpleFoam (isothermal)   default 1
#                     2 = buoyantSimpleFoam
#   --mesh    m0|m1|m2|m3                           default m2
#                     m0/m1/m2 is the independence ladder; m3 is NOT buildable
#   --Q       M3H     fan volumetric flow, m3/h     default 1.25
#                     ladder is 5 / 2.5 / 1.25; 5 is FREE AIR, an upper bound
#   --g       VALUE   gravity magnitude, m/s2       default 9.81
#   --led     WATTS   LED panel power (phase 2)     default 38.4
#   --model   kOmegaSST|laminar                     default kOmegaSST
#
#   --transient       time-accurate run: phase 1 -> pimpleFoam,
#                     phase 2 -> buoyantPimpleFoam (CLAUDE.md 5.1 phase 2b).
#                     Needed when the flow will not settle -- see the m1
#                     baseline, where a confined jet at Re_port = 5832 flaps
#                     and simpleFoam cannot converge on it.
#   --endTime   S     transient end time, seconds   default 6.6 * tau
#   --avgStart  S     start time averaging, seconds default 2.75 * tau
#
# The transient defaults are multiples of the residence time tau = V_air / Q, so
# they scale correctly with --Q: a lower flow rate has a proportionally longer
# tau and needs a proportionally longer run to collect the same statistics.
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Q default is 1.25 m3/h, NOT the 5 m3/h datasheet figure (changed 2026-08-14).
# 5 is the LD3007MS FREE-AIR rating -- zero back-pressure -- and CLAUDE.md 6.2
# estimates this chamber presents >= 30 Pa of load, at or beyond the shut-off of
# a 30 mm axial fan, on top of a 30 mm fan blowing into a 20 mm hole (44 % of the
# face area). The delivered flow is "plausibly half or less". 1.25 is the bottom
# rung of the 5 / 2.5 / 1.25 ladder and the most likely of the three to bracket
# the real operating point. It is also 4x cheaper to run transient, because the
# Courant-limited dt scales as 1/U.
#
# This is still a PLACEHOLDER pending the Dp-Q curve (CLAUDE.md 10.2). It is a
# better-motivated placeholder than 5, not a measurement.
NAME="" ; PHASE=1 ; MESH=m2 ; Q_M3H=1.25 ; GVAL=9.81 ; LED=38.4 ; MODEL=kOmegaSST
TRANSIENT=0 ; END_TIME="" ; AVG_START="" ; JETREFINE=0

# Run length and averaging window, as multiples of tau.
#   6.60 tau  total  -- long enough for statistics after the startup is thrown away
#   2.75 tau  discarded -- start-from-rest needs ~3 flow-throughs to forget the
#             initial condition; averaging over it is the classic way to get a
#             confidently wrong mean
N_TAU_END=6.6 ; N_TAU_AVG=2.75

while [ $# -gt 0 ]; do
    case "$1" in
        --name)      NAME=$2  ; shift 2 ;;
        --phase)     PHASE=$2 ; shift 2 ;;
        --mesh)      MESH=$2  ; shift 2 ;;
        --Q)         Q_M3H=$2 ; shift 2 ;;
        --g)         GVAL=$2  ; shift 2 ;;
        --led)       LED=$2   ; shift 2 ;;
        --model)     MODEL=$2 ; shift 2 ;;
        --transient) TRANSIENT=1 ; shift 1 ;;
        --jetRefine) JETREFINE=1 ; shift 1 ;;
        --endTime)   END_TIME=$2  ; shift 2 ;;
        --avgStart)  AVG_START=$2 ; shift 2 ;;
        *) echo "unknown option: $1" >&2 ; exit 1 ;;
    esac
done
if [ "$TRANSIENT" = 0 ] && { [ -n "$END_TIME" ] || [ -n "$AVG_START" ]; }; then
    echo "--endTime/--avgStart are transient-only; add --transient" >&2 ; exit 1
fi
[ -n "$NAME" ] || { echo "--name is required" >&2 ; exit 1 ; }

CASE="$ROOT/runs/$NAME"
[ -e "$CASE" ] && { echo "runs/$NAME already exists -- remove it first" >&2 ; exit 1 ; }

# etc/bashrc, not /usr/bin/openfoam2606 -- the latter is `exec .../etc/openfoam`
# and replaces this shell with an interactive session, silently discarding
# everything below. Verified 2026-08-14.
# etc/bashrc is not written for `set -eu`: it reads WM_PROJECT_SITE unset, and
# its optional `_foamEtc -config adios2/hdf5/CGAL` probes return non-zero for
# packages this build does not ship. Under `set -e` that aborts the source
# part-way through and bash reports `pop_var_context: head of shell_variables
# not a function context`. Lift both flags across the source, restore after.
set +eu
# shellcheck disable=SC1091
. /usr/lib/openfoam/openfoam2606/etc/bashrc
set -eu

mkdir -p "$ROOT/runs"
cp -r "$ROOT/templates" "$CASE"
rm -rf "$CASE/0.orig.phase2" "$CASE/transient"
chmod +x "$CASE/Allrun" "$CASE/Allclean"
cd "$CASE"

# --- resolution (CLAUDE.md 7). Background block, includes the 1-cell margin. --
# m0 is the COARSE rung of the mesh-independence ladder, added 2026-08-14 because
# m3 is not buildable: it extrapolates to ~33 M cells against a maxGlobalCells cap
# of 20 M, so snappy would silently under-refine and hand back a mesh that is not
# the level it claims -- the worst possible failure for an independence study
# (CLAUDE.md 7). The ladder therefore runs DOWNWARD from m2, not upward from m1.
#
# m0 is the one rung that cannot divide exactly. The internal dims are 360/560/430
# thirds-of-a-mm and their GCD is 10, so base = 10/3 mm -- i.e. m1 -- is the
# LARGEST base cell that divides all three exactly, and no coarser rung can.
# Halving the background block confirms it: 38/2 and 58/2 are integers, 45/2 is
# not. z therefore takes 23 cells of 6.522 mm against 6.667 mm in x and y, a 2.2 %
# anisotropy (aspect ratio 1.02). That is irrelevant here -- the background patch
# is entirely consumed by snappy, and the hood is a curved surface that never lay
# on a cell boundary at any level anyway.
case "$MESH" in
    m0) NX=19  ; NY=29  ; NZ=23  ;;
    m1) NX=38  ; NY=58  ; NZ=45  ;;
    m2) NX=76  ; NY=116 ; NZ=90  ;;
    m3) NX=152 ; NY=232 ; NZ=180 ;;
    *)  echo "--mesh must be m0, m1, m2 or m3" >&2 ; exit 1 ;;
esac
if [ "$MESH" = m3 ]; then
    echo "!! m3 extrapolates to ~33 M cells against maxGlobalCells 20000000." >&2
    echo "!! snappy will stop refining SILENTLY and produce a mesh that is not" >&2
    echo "!! level 3 (CLAUDE.md 7). Raise the cap deliberately, or use m0/m1/m2." >&2
fi
# NOT foamDictionary here. `foamDictionary -set` rewrites the whole file through
# the parser, which EXPANDS $nx/$ny/$nz into `blocks (hex ... (76 116 90) ...)`
# on the very first call -- after which setting nx/ny/nz has no effect at all
# and every case silently comes out at the template default (m2). That would
# have quietly voided the mesh-independence study. It also rounds the vertex
# coordinates to writePrecision, losing the exact 10/3 mm spans. Edit in place.
sed -i -e "s/^nx  *[0-9][0-9]*;/nx  $NX;/" \
       -e "s/^ny  *[0-9][0-9]*;/ny  $NY;/" \
       -e "s/^nz  *[0-9][0-9]*;/nz  $NZ;/" system/blockMeshDict
# Fail loudly rather than silently meshing the wrong level.
grep -q "^nx  $NX;" system/blockMeshDict \
  && grep -q "^ny  $NY;" system/blockMeshDict \
  && grep -q "^nz  $NZ;" system/blockMeshDict \
  || { echo "failed to set resolution in system/blockMeshDict" >&2 ; exit 1 ; }

# --- tray refinement: TOPOLOGY, not accuracy (m0 only) ----------------------
# The 2.5 mm tray side slots are open flow paths (CLAUDE.md 6.1) and they close
# completely if the local cell is not small enough to fit through them. Measured
# 2026-08-14 at m0 with the template's level 2 (6.667/4 = 1.667 mm, 1.5 cells
# across the slot): snappy sealed both slots and checkMesh reported a total
# volume of 2.5147e-3 m3 against V_air 2.5302e-3 -- a 15.5 mL deficit, which is
# 99 % of the 15.6 mL slot volume. It is a clean pass, silently solving a
# DIFFERENT CHAMBER. It also kills the run at the first write, because the
# traySlotFlux function object samples a plane that then has no faces.
#
# Level 3 at m0 gives 0.833 mm, 3 cells across, and restores the volume to
# 2.53008e-3 (0.12 mL deficit). Cost is 205 k -> 380 k cells.
#
# NOTE this makes the slot cell size 0.833 / 0.833 / 0.417 mm across m0/m1/m2 --
# i.e. the m0 -> m1 step does NOT refine the slots, it only refines everything
# else. That is deliberate: preserving the flow topology matters more than a
# uniform refinement ratio on a feature carrying 0.23 % of Q (CLAUDE.md 10.3).
# State it when reporting the independence study.
if [ "$MESH" = m0 ]; then
    sed -i -e 's|^            level       (2 2);|            level       (3 3);|' \
           -e 's|^                tray    { level (2 2);|                tray    { level (3 3);|' \
           -e 's|traySlotLeft  { mode inside; levels ((1e15 2)); }|traySlotLeft  { mode inside; levels ((1e15 3)); }|' \
           -e 's|traySlotRight { mode inside; levels ((1e15 2)); }|traySlotRight { mode inside; levels ((1e15 3)); }|' \
           system/snappyHexMeshDict
    [ "$(grep -c '(3 3)' system/snappyHexMeshDict)" -eq 2 ] \
      && [ "$(grep -c '1e15 3' system/snappyHexMeshDict)" -eq 2 ] \
      || { echo "failed to raise tray refinement for m0" >&2 ; exit 1 ; }
    echo "  m0: tray refinement raised to level 3 to keep the side slots open"
fi

# --- jet shear-layer refinement (opt-in) ------------------------------------
# Adds the `jetShear` region at ONE LEVEL ABOVE inletJet. See snappyHexMeshDict
# for the geometry and for why this is opt-in rather than default.
if [ "$JETREFINE" = 1 ]; then
    JETLEVEL=3
    sed -i "s|^        traySlotLeft |        jetShear      { mode inside; levels ((1e15 $JETLEVEL)); }\n        traySlotLeft |" \
        system/snappyHexMeshDict
    grep -q "jetShear      { mode inside" system/snappyHexMeshDict \
      || { echo "failed to enable jetShear refinement" >&2 ; exit 1 ; }
    echo "  jetRefine: jetShear region enabled at level $JETLEVEL (inlet shear layer)"
fi

# --- fan flow rate ----------------------------------------------------------
# 5 m3/h is the LD3007MS FREE-AIR rating, an upper bound (CLAUDE.md 6.2).
Q_M3S=$(awk -v q="$Q_M3H" 'BEGIN{printf "%.6e", q/3600.0}')
U_IN=$(awk  -v q="$Q_M3S" 'BEGIN{printf "%.4f", q/3.14159265e-4}')
RE=$(awk    -v u="$U_IN"  'BEGIN{printf "%.0f", u*0.02/1.516e-5}')
foamDictionary -entry "boundaryField/inlet/volumetricFlowRate" -set "$Q_M3S" 0.orig/U > /dev/null 2>&1

# tau is needed by the transient block below, so derive it here rather than
# down with the rest of the notes arithmetic.
V_AIR=2.530e-3          # m3, NOT litres -- do not divide by 1000 again
ACH=$(awk -v q="$Q_M3H" -v v="$V_AIR" 'BEGIN{printf "%.0f", q/v}')
TAU=$(awk -v q="$Q_M3S" -v v="$V_AIR" 'BEGIN{printf "%.2f", v/q}')

# --- gravity (CLAUDE.md 5.2) ------------------------------------------------
foamDictionary -entry value -set "(0 0 -$GVAL)" constant/g > /dev/null 2>&1

# --- turbulence model -------------------------------------------------------
if [ "$MODEL" = laminar ]; then
    foamDictionary -entry simulationType -set laminar constant/turbulenceProperties > /dev/null 2>&1
else
    foamDictionary -entry RAS/RASModel -set "$MODEL" constant/turbulenceProperties > /dev/null 2>&1
fi

# Re_port decides whether the model is defensible (CLAUDE.md 5.2). Warn; do NOT
# auto-switch. CLAUDE.md 5.2 is explicit that the right response to the
# transitional band is to "run the baseline both ways at the chosen Q and report
# the spread as a modelling uncertainty" -- silently picking one would destroy
# exactly the comparison the project needs, and would also break the
# one-change-per-run rule by coupling the model to the flow rate.
if [ "$MODEL" != laminar ] && [ "$RE" -lt 2300 ]; then
    echo "  !! Re_port = $RE is LAMINAR (< 2300) and this case uses $MODEL."
    echo "     CLAUDE.md 5.2 puts Q = 1.25 m3/h in the laminar band. A turbulent"
    echo "     RAS closure there produces spurious nut and over-mixes."
    echo "     Generate the pair and report the spread:"
    echo "         --model laminar    (expected to be the defensible one here)"
    echo "         --model kOmegaSST  (this run)"
elif [ "$MODEL" != laminar ] && [ "$RE" -lt 4000 ]; then
    echo "  !! Re_port = $RE is TRANSITIONAL (2300-4000) -- neither laminar nor a"
    echo "     fully turbulent closure is defensible. CLAUDE.md 5.2: run both ways."
fi

# --- can this mesh resolve the LAMINAR shear layer? -------------------------
# Diagnosed 2026-08-14 (CLAUDE.md 7). With a top-hat inlet BC on a plain cutout
# the shear layer starts at zero thickness and grows as delta ~ sqrt(nu*x/U), so
# it is resolved only beyond x_res = h^2 * U / nu, where h is the cell at the
# port (base/4, since inlet/outlet are refinementSurfaces level 2, or base/8
# with --jetRefine).
#
# ⚠ This is a RESOLUTION criterion, not a convergence one. Tested and refuted
# 2026-08-14: across a 16x range in x_res (202 / 50.6 / 12.7 mm) the steady
# laminar p residual went 1.4e-1 / 2.7e-1 / 1.4e-1 -- non-monotone, never within
# four orders of the 1e-5 target. The flow at Q = 1.25 m3/h is GENUINELY
# UNSTEADY and no mesh fixes that. What x_res tells you is what a faithful
# TRANSIENT needs.
#
# This does NOT apply to the RANS arm: its nut (measured 5x molecular) thickens
# the layer by sqrt(6) and hides the problem.
if [ "$MODEL" = laminar ]; then
    BASE_MM=$(awk -v n="$NX" 'BEGIN{printf "%.6f", 126.6667/n}')
    DIV=$([ "$JETREFINE" = 1 ] && echo 8 || echo 4)
    XRES=$(awk -v b="$BASE_MM" -v d="$DIV" -v u="$U_IN" \
        'BEGIN{h=b/d/1000; printf "%.1f", h*h*u/1.516e-5*1000}')
    echo "  laminar shear layer: cell at port $(awk -v b="$BASE_MM" -v d="$DIV" 'BEGIN{printf "%.3f", b/d}') mm"\
         "-> resolved beyond x = ${XRES} mm of the 186.7 mm path"
    if awk -v x="$XRES" 'BEGIN{exit !(x > 186.7)}'; then
        echo "  !! x_res = ${XRES} mm EXCEEDS the 186.7 mm chamber depth -- the inlet"
        echo "     shear layer is NEVER resolved anywhere in this mesh. The jet is"
        echo "     carried entirely by numerical diffusion, which artificially damps"
        echo "     the unsteadiness (measured: m0 reports +-3.0 % tray fluctuation"
        echo "     where m1 reports +-18.2 %). Do not read a calm result here as a"
        echo "     steady flow. Add --jetRefine (+25 % cells) or use a finer mesh."
    elif awk -v x="$XRES" 'BEGIN{exit !(x > 46.7)}'; then
        echo "  !! x_res = ${XRES} mm is more than a quarter of the path -- the jet is"
        echo "     under-resolved where it matters most. --jetRefine cuts x_res 4x"
        echo "     for +25 % cells, vs +460 % for the next mesh level."
    fi
    if [ "$TRANSIENT" = 0 ]; then
        echo "  !! STEADY laminar at this Q: expect it NOT to converge. Measured"
        echo "     2026-08-14 at Q=1.25 across a 16x resolution range, the p residual"
        echo "     plateaued at 1.4e-1 / 2.7e-1 / 1.4e-1 -- non-monotone, never within"
        echo "     four orders of the 1e-5 target. The flow is genuinely unsteady at"
        echo "     BOTH ends of the Q ladder (CLAUDE.md 5.1). Use --transient."
    fi
fi

# --- steady or transient ----------------------------------------------------
# Swap the whole of system/ over to the transient variants BEFORE the phase
# block, so the phase block's `application` edit lands on whichever controlDict
# is actually in place.
if [ "$TRANSIENT" = 1 ]; then
    cp -r "$ROOT/templates/transient/system/." system/
    [ -n "$END_TIME" ]  || END_TIME=$(awk  -v t="$TAU" -v n="$N_TAU_END" 'BEGIN{printf "%.2f", t*n}')
    [ -n "$AVG_START" ] || AVG_START=$(awk -v t="$TAU" -v n="$N_TAU_AVG" 'BEGIN{printf "%.2f", t*n}')

    awk -v e="$END_TIME" -v a="$AVG_START" 'BEGIN{
        if (a+0 >= e+0) { print "avgStart must be < endTime" > "/dev/stderr"; exit 1 }
    }' || exit 1

    sed -i "s/^endTime         12;/endTime         $END_TIME;/" system/controlDict
    grep -q "^endTime         $END_TIME;" system/controlDict \
      || { echo "failed to set endTime in system/controlDict" >&2 ; exit 1 ; }

    sed -i "s/__AVG_START__/$AVG_START/" system/functions/transientMonitors
    # `if`, not `grep ... && { }` -- under `set -e` the latter's exit status is
    # the grep's, and a NOT-found placeholder (the success case) reads as failure.
    if grep -q "__AVG_START__" system/functions/transientMonitors; then
        echo "failed to set timeStart in functions/transientMonitors" >&2 ; exit 1
    fi
fi

# --- phase ------------------------------------------------------------------
if [ "$PHASE" = 2 ]; then
    cp "$ROOT/templates/0.orig.phase2/"* 0.orig/
    foamDictionary -entry "boundaryField/hood/Q" -set "$LED" 0.orig/T > /dev/null 2>&1
    SOLVER=$( [ "$TRANSIENT" = 1 ] && echo buoyantPimpleFoam || echo buoyantSimpleFoam )
else
    SOLVER=$( [ "$TRANSIENT" = 1 ] && echo pimpleFoam || echo simpleFoam )
    LED="n/a (isothermal)"
fi

# sed, not foamDictionary: controlDict carries `#include "functions/..."`
# directives that the parser would expand inline on rewrite, defeating the
# convention in CLAUDE.md 8.4.
sed -i "s/^application     [A-Za-z]*;/application     $SOLVER;/" system/controlDict
grep -q "^application     $SOLVER;" system/controlDict \
  || { echo "failed to set application in system/controlDict" >&2 ; exit 1 ; }

# --- derived quantities, for the notes --------------------------------------
# V_AIR / ACH / TAU are set above, before the transient block that needs TAU.
if [ "$PHASE" = 2 ]; then
    DT=$(awk -v p="$LED" -v q="$Q_M3S" 'BEGIN{printf "%.1f", p/(q*1.2*1004.5)}')
else
    DT="n/a"
fi

cat > NOTES.md <<EOF
# $NAME

Generated $(date -Iseconds) by scripts/generate_case.sh -- do not hand-edit this case.

## Parameters

| | |
|---|---|
| Phase / solver | $PHASE / \`$SOLVER\` |
| Time treatment | $( [ "$TRANSIENT" = 1 ] \
      && echo "**transient**, endTime $END_TIME s = $(awk -v e="$END_TIME" -v t="$TAU" 'BEGIN{printf "%.1f", e/t}') tau, averaging from $AVG_START s = $(awk -v a="$AVG_START" -v t="$TAU" 'BEGIN{printf "%.1f", a/t}') tau" \
      || echo "steady" ) |
| Mesh level | $MESH ($NX x $NY x $NZ background) |
| Turbulence | $MODEL |
| Q | $Q_M3H m3/h = $Q_M3S m3/s |
| U_in | $U_IN m/s |
| Re_port | $RE |
| ACH | $ACH h^-1 |
| tau (residence) | $TAU s |
| g | $GVAL m/s2 |
| LED power | $LED W |
| Predicted bulk dT | $DT K |

## Caveats carried by this run

- **Q = $Q_M3H m3/h — still a PLACEHOLDER.** The LD3007MS is rated 5 m3/h in
  **free air** (zero back-pressure); CLAUDE.md 6.2 estimates this chamber loads
  it to >= 30 Pa, at or beyond a 30 mm axial fan's shut-off, so the delivered
  flow is "plausibly half or less". The ladder is 5 / 2.5 / 1.25 and the default
  is now the bottom rung. The operating point stays unknown pending the Dp-Q
  curve (CLAUDE.md 10.2). Every metric here is a function of this number.
- **Re_port = $RE.** See CLAUDE.md 5.2 for whether \`$MODEL\` is defensible at
  this Reynolds number: < 2300 laminar, 2300-4000 transitional, > 4000 turbulent.
  In the lower two bands the answer is to run it BOTH ways and report the spread
  as a modelling uncertainty, not to pick one.
$( [ "$PHASE" = 2 ] && cat <<'P2'
- **LED power is a PLACEHOLDER.** 38.4 W = 50 % of full white. The CLAUDE.md 6.3
  energy balance says the chamber needs ~5 W to hold 22-25 C. Absolute
  temperatures from this run are NOT a prediction of the built chamber --
  the flow and stratification STRUCTURE is what is informative.
- Stable stratification (LED on the ceiling) may prevent steady convergence.
  If residuals plateau or oscillate, switch to buoyantPimpleFoam. Do not
  relax it into a false steady answer.
P2
)
- Hood/lip junction geometry is +-1 mm over the bottom ~4 mm of the flank.
- Tray has **no boundary layers** (slot too tight) -- do not report tray wall shear.

## Question

TBD -- what is this run for?

## Answer

TBD -- fill in after checking CLAUDE.md 9 acceptance criteria.
EOF

echo "created runs/$NAME"
echo "  solver     $SOLVER   mesh $MESH ($NX x $NY x $NZ)   model $MODEL"
echo "  Q          $Q_M3H m3/h  ->  U_in $U_IN m/s   Re_port $RE   ACH $ACH   tau ${TAU}s"
[ "$PHASE" = 2 ] && echo "  LED        $LED W  ->  predicted bulk dT $DT K"
echo
echo "  cd runs/$NAME && ./Allrun"
