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
#   --mesh    m1|m2|m3                              default m2
#   --Q       M3H     fan volumetric flow, m3/h     default 5
#   --g       VALUE   gravity magnitude, m/s2       default 9.81
#   --led     WATTS   LED panel power (phase 2)     default 38.4
#   --model   kOmegaSST|laminar                     default kOmegaSST
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="" ; PHASE=1 ; MESH=m2 ; Q_M3H=5 ; GVAL=9.81 ; LED=38.4 ; MODEL=kOmegaSST

while [ $# -gt 0 ]; do
    case "$1" in
        --name)  NAME=$2  ; shift 2 ;;
        --phase) PHASE=$2 ; shift 2 ;;
        --mesh)  MESH=$2  ; shift 2 ;;
        --Q)     Q_M3H=$2 ; shift 2 ;;
        --g)     GVAL=$2  ; shift 2 ;;
        --led)   LED=$2   ; shift 2 ;;
        --model) MODEL=$2 ; shift 2 ;;
        *) echo "unknown option: $1" >&2 ; exit 1 ;;
    esac
done
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
rm -rf "$CASE/0.orig.phase2"
chmod +x "$CASE/Allrun" "$CASE/Allclean"
cd "$CASE"

# --- resolution (CLAUDE.md 7). Background block, includes the 1-cell margin. --
case "$MESH" in
    m1) NX=38  ; NY=58  ; NZ=45  ;;
    m2) NX=76  ; NY=116 ; NZ=90  ;;
    m3) NX=152 ; NY=232 ; NZ=180 ;;
    *)  echo "--mesh must be m1, m2 or m3" >&2 ; exit 1 ;;
esac
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

# --- fan flow rate ----------------------------------------------------------
# 5 m3/h is the LD3007MS FREE-AIR rating, an upper bound (CLAUDE.md 6.2).
Q_M3S=$(awk -v q="$Q_M3H" 'BEGIN{printf "%.6e", q/3600.0}')
U_IN=$(awk  -v q="$Q_M3S" 'BEGIN{printf "%.4f", q/3.14159265e-4}')
RE=$(awk    -v u="$U_IN"  'BEGIN{printf "%.0f", u*0.02/1.516e-5}')
foamDictionary -entry "boundaryField/inlet/volumetricFlowRate" -set "$Q_M3S" 0.orig/U > /dev/null 2>&1

# --- gravity (CLAUDE.md 5.2) ------------------------------------------------
foamDictionary -entry value -set "(0 0 -$GVAL)" constant/g > /dev/null 2>&1

# --- turbulence model -------------------------------------------------------
if [ "$MODEL" = laminar ]; then
    foamDictionary -entry simulationType -set laminar constant/turbulenceProperties > /dev/null 2>&1
else
    foamDictionary -entry RAS/RASModel -set "$MODEL" constant/turbulenceProperties > /dev/null 2>&1
fi

# --- phase ------------------------------------------------------------------
if [ "$PHASE" = 2 ]; then
    cp "$ROOT/templates/0.orig.phase2/"* 0.orig/
    # sed, not foamDictionary: controlDict carries `#include "functions/..."`
    # directives that the parser would expand inline on rewrite, defeating the
    # convention in CLAUDE.md 8.4.
    sed -i "s/^application     simpleFoam;/application     buoyantSimpleFoam;/" \
        system/controlDict
    grep -q "^application     buoyantSimpleFoam;" system/controlDict \
      || { echo "failed to set application in system/controlDict" >&2 ; exit 1 ; }
    foamDictionary -entry "boundaryField/hood/Q" -set "$LED" 0.orig/T > /dev/null 2>&1
    SOLVER=buoyantSimpleFoam
else
    SOLVER=simpleFoam
    LED="n/a (isothermal)"
fi

# --- derived quantities, for the notes --------------------------------------
V_AIR=2.530e-3          # m3, NOT litres -- do not divide by 1000 again
ACH=$(awk -v q="$Q_M3H" -v v="$V_AIR" 'BEGIN{printf "%.0f", q/v}')
TAU=$(awk -v q="$Q_M3S" -v v="$V_AIR" 'BEGIN{printf "%.2f", v/q}')
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

- **Q = $Q_M3H m3/h.** 5 m3/h is the LD3007MS **free-air** rating, not the delivered
  flow. The real operating point is lower and unknown pending the Dp-Q curve
  (CLAUDE.md 10.2). Every metric here is a function of this number.
- **Re_port = $RE.** See CLAUDE.md 5.2 for whether \`$MODEL\` is defensible at
  this Reynolds number. Transitional (2300-4000) means run it both ways.
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
