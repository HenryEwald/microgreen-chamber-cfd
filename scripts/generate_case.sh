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
#   --Q       M3H     fan volumetric flow, m3/h     default: SOLVED from the
#                     fan curve against the system curve for the chosen --portD.
#                     Pass it only to force an operating point off that curve;
#                     the script warns when you do.
#   --portD   MM      port diameter, both ports     default 40
#   --diffuser DEG    inlet vane angle              default none (control)
#   --diffuserType cascade|radial                   default cascade
#                     cascade = horizontal turning vanes, DEG = downward tilt
#                     radial  = swirl diffuser, DEG = vane cant (S grows with it)
#   --vanes   N       vanes in the diffuser         default 5
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
#   --frames    N     write times over the run     default 60
#                     writeInterval = endTime/N, and purgeWrite is 0, so
#                     EVERY frame is kept and the run is animatable. The
#                     generator projects the disk cost and warns.
#
# The transient defaults are multiples of the residence time tau = V_air / Q, so
# they scale correctly with --Q: a lower flow rate has a proportionally longer
# tau and needs a proportionally longer run to collect the same statistics.
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# ---------------------------------------------------------------------------
# Q is no longer a constant. HISTORY, because two of these were retracted and
# should not be re-derived:
#
#  2026-08-14  default moved 5 -> 1.25 m3/h. 5 is the LD3007MS FREE-AIR rating
#              at zero back-pressure; the chamber presents >= 30 Pa, at or past
#              a 30 mm axial fan's shut-off, so delivered flow was "plausibly
#              half or less" and 1.25 was the ladder rung most likely to
#              bracket it.
#  2026-08-15  RETRACTED the cost half of that argument. "Low Q is 4x cheaper
#              transient" is WRONG: dt ~ 1/U but tau = V_air/Q ~ 1/Q too, so a
#              6.6-tau run is the SAME step count at every flow rate. The
#              free-air argument was untouched and carried the choice alone.
#  2026-08-16  default is now SOLVED, not chosen, because the fan and the port
#              both changed and Q is a consequence of them rather than a free
#              parameter. See the fan block below.
#
# Note the cost identity above assumed a FIXED port. It does not survive the
# port change: steps ~ endTime/dt ~ (1/Q)/(1/U) = U/Q ~ 1/A, so quadrupling the
# port area makes the transient ~4x CHEAPER (~5 h vs ~20 h at m0+jetRefine).
# Q rises 9.4x but U_in only 2.35x, and it is U that sets dt.
#
# NOTE the interaction with --led: dT scales as 1/Q, so the LED ceiling moves
# with the flow rate. At Q = 1.25 it was ~1.3 W for a 3 K rise; at the Oe 40
# operating point (~11.8 m3/h) it is ~12 W. The phase-2 block below computes it.
NAME="" ; PHASE=1 ; MESH=m2 ; Q_M3H="" ; GVAL=9.81 ; LED=38.4 ; MODEL=kOmegaSST
TRANSIENT=0 ; END_TIME="" ; AVG_START="" ; JETREFINE=0
PORT_D_MM=40 ; DIFF_TILT="" ; DIFF_VANES="" ; DIFF_TYPE=cascade
FRAMES=60

# --- fan, and why Q is now DERIVED rather than defaulted ---------------------
# The fan changed on 2026-08-16: LD3007MS (30x30x7 mm, 5 m3/h free air) ->
# Sunon MF50100V2-1000U-A99 (50x50x10 mm, 5 VDC, 0.085 A, 430 mW, 4800 rpm,
# 11.0 CFM = 18.69 m3/h free air, 0.110 inch-H2O = 27.4 Pa shut-off).
#
# It is a FLOW upgrade, not a PRESSURE one -- 27.4 Pa shut-off is the same class
# as the part it replaces, because that is simply what axial fans are. Against a
# Q^2 system curve the PORT DIAMETER therefore does most of the work: the loss
# goes as D^-4, so Oe 20 -> Oe 40 takes the delivered flow 4.25 -> 11.8 m3/h off
# the same fan.
#
# That coupling is exactly why Q is no longer a hard-coded default. Changing
# --portD without changing --Q used to leave the case running the old flow rate
# through a new hole, which is not a physical operating point at all. Q is now
# solved from the fan curve and the system curve unless --Q overrides it.
#
#   fan    : dp = DPMAX * (1 - Q/QFREE)        linear between the two datasheet
#                                              endpoints; the real mid-curve is
#                                              a plot image on page 5 of the PDF
#   system : dp = KSYS * 0.5 * rho * (Q/A)^2   KSYS = 2.5 = 1.0 port dynamic
#                                              head + 0.5 inlet contraction
#                                              + 1.0 outlet discharge (6.2)
#
# STILL A PLACEHOLDER, for a different reason than before: the endpoints are
# measured, the mid-curve shape and KSYS are estimates. Measure the delivered
# flow before publishing anything (CLAUDE.md 10.2 item 1).
FAN_QFREE=18.69 ; FAN_DPMAX=27.4 ; KSYS=2.5 ; RHO_AIR=1.2

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
        --portD)     PORT_D_MM=$2 ; shift 2 ;;
        --diffuser)  DIFF_TILT=$2 ; shift 2 ;;
        --vanes)     DIFF_VANES=$2 ; shift 2 ;;
        --diffuserType) DIFF_TYPE=$2 ; shift 2 ;;
        --frames)    FRAMES=$2 ; shift 2 ;;
        --endTime)   END_TIME=$2  ; shift 2 ;;
        --avgStart)  AVG_START=$2 ; shift 2 ;;
        *) echo "unknown option: $1" >&2 ; exit 1 ;;
    esac
done
# --avgStart is meaningless without a time axis; --endTime is not. For a steady
# run "time" is the SIMPLE iteration count, and being able to cap it is what
# makes a cheap smoke test possible -- which is how the missing `rhoFinal` in
# the buoyant path was found (2026-08-15). Without this the only way to
# exercise buoyantSimpleFoam was to launch all 4000 iterations of it.
if [ "$TRANSIENT" = 0 ] && [ -n "$AVG_START" ]; then
    echo "--avgStart is transient-only; add --transient" >&2 ; exit 1
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

# --- tray refinement -------------------------------------------------------
# REMOVED 2026-08-16. m0 used to get a level-3 override on the tray here.
#
# That override was TOPOLOGY, not accuracy: at level 2 the m0 cell is 1.667 mm,
# only 1.5 cells across the 2.5 mm tray side slots, and snappy sealed both. The
# result was a clean checkMesh pass that silently solved a DIFFERENT CHAMBER --
# total volume 2.5147e-3 m3 against V_air 2.5302e-3, a 15.5 mL deficit that was
# 99 % of the slot volume. Level 3 restored it, at 205 k -> 380 k cells.
#
# The flush tray has no slots, so there is nothing left to seal and no reason to
# pay for level 3. m0 goes back to the template's level 2 and roughly halves.
#
# The habit that override taught is still the right one, and it is now the ONLY
# guard on this class of error: ALWAYS check total volume against V_air, never
# just "Mesh OK". templates/Allrun does this. A sealed feature is invisible to
# every other mesh metric.

# --- geometry: port size and the inlet diffuser ------------------------------
# Run the generator NOW, at generation time, rather than leaving it to Allrun.
# Two reasons: it verifies the surfaces before the case is even handed over, and
# it emits constant/triSurface/geometry.info, which is where the port area and
# V_air below come from. Those were previously HARD-CODED CONSTANTS in this
# script (3.14159265e-4 and 2.3296e-3) -- duplicated from make_geometry.py, and
# duplicated constants are precisely what drifted when the tray went flush.
PORT_R_M=$(awk -v d="$PORT_D_MM" 'BEGIN{printf "%.6f", d/2000.0}')
GEOM_ARGS="--port-r $PORT_R_M"
if [ -n "$DIFF_TILT" ]; then
    GEOM_ARGS="$GEOM_ARGS --diffuser-type $DIFF_TYPE --diffuser-tilt $DIFF_TILT"
    [ -n "$DIFF_VANES" ] && GEOM_ARGS="$GEOM_ARGS --diffuser-vanes $DIFF_VANES"
fi

# Allrun regenerates the geometry if the STLs are missing, so it needs the same
# arguments. Carrying them in the case (rather than re-deriving them) is what
# keeps a regenerated surface identical to the one that was verified here.
printf '%s\n' "$GEOM_ARGS" > system/geometryArgs

python3 "$ROOT/scripts/make_geometry.py" --case . $GEOM_ARGS --verify \
    > log.makeGeometry 2>&1 \
  || { echo "geometry generation FAILED:" >&2; cat log.makeGeometry >&2; exit 1; }

_geom() { awk -v k="$1" '$1==k{print $2}' constant/triSurface/geometry.info; }
A_PORT=$(_geom PORT_AREA)
V_AIR=$(_geom V_AIR)          # m3, NOT litres -- do not divide by 1000 again
[ -n "$A_PORT" ] && [ -n "$V_AIR" ] \
  || { echo "geometry.info missing PORT_AREA/V_AIR" >&2 ; exit 1 ; }

# --- port-sized refinement regions ------------------------------------------
# inletJet / outletJet / jetShear hug the port, so they have to MOVE WITH IT.
# They were written for Oe 20 and would have left the Oe 40 jet refined over
# only its middle half -- which passes checkMesh, produces a plausible field,
# and is wrong. Margins are the ones the dict documents: 10 mm around the port
# for the jet boxes, 4 mm for the shear box.
#
# NOT foamDictionary. `foamDictionary -set` REWRITES THE WHOLE FILE from the
# parsed dictionary, which silently discards every comment in it -- measured
# here, snappyHexMeshDict went 300 -> 255 lines and lost all of its
# documentation, including the anchor the jetShear insertion below greps for.
# The comments in that dict are the record of why each refinement level is what
# it is (CLAUDE.md 7), so losing them is not cosmetic.
#
# Targeted in-place edit instead: rewrite only the min/max lines inside the
# named block, and assert afterwards that all six landed.
python3 - "$PORT_R_M" <<'PY'
import re, sys
r = float(sys.argv[1])
PX, PZ, SPRING = 0.060, 0.066667, 0.096667
# name -> (x/z margin, y_min, y_max)
BOXES = {"inletJet":  (0.010, -0.001, 0.050),
         "outletJet": (0.010,  0.136, 0.188),
         "jetShear":  (0.004, -0.001, 0.030)}
p = "system/snappyHexMeshDict"
s = open(p).read()
n = 0
for name, (m, y0, y1) in BOXES.items():
    # clamp z above the hood spring line: the hood's own surface refinement
    # already covers that region, and the box would only duplicate it.
    lo = "(%.6f %.6g %.6f)" % (PX - r - m, y0, PZ - r - m)
    hi = "(%.6f %.6g %.6f)" % (PX + r + m, y1, min(PZ + r + m, SPRING))
    blk = re.search(r"(^    %s\s*\n    \{.*?^    \})" % re.escape(name),
                    s, re.S | re.M)
    if blk is None:
        raise SystemExit("refinement region %s not found" % name)
    body = blk.group(1)
    new = re.sub(r"^(\s*min\s+)\S.*?;", r"\g<1>%s;" % lo, body, count=1, flags=re.M)
    new = re.sub(r"^(\s*max\s+)\S.*?;", r"\g<1>%s;" % hi, new,  count=1, flags=re.M)
    if new == body:
        raise SystemExit("failed to rewrite min/max in %s" % name)
    s = s[:blk.start(1)] + new + s[blk.end(1):]
    n += 2
open(p, "w").write(s)
print("  ports     rescaled %d refinement-region bounds" % n)
PY
echo "  ports     Oe${PORT_D_MM} mm, A = ${A_PORT} m2"

# --- inlet vane diffuser ----------------------------------------------------
# Three insertions, all conditional on --diffuser, because the control arm has
# no diffuser.stl and snappy fails hard on a triSurfaceMesh with no file.
if [ -n "$DIFF_TILT" ]; then
    python3 - "$DIFF_TILT" <<'PY'
import re, sys
tilt = sys.argv[1]
p = "system/snappyHexMeshDict"
s = open(p).read()

geom = '''    diffuser.stl
    {
        type        triSurfaceMesh;
        name        diffuser;
        regions
        {
            diffuser { name diffuser; }
        }
    }

'''
anchor = "    // diffuser.stl is INSERTED HERE"
assert anchor in s, "geometry anchor missing from snappyHexMeshDict"
s = s.replace(anchor, geom + anchor, 1)

surf = '''        diffuser
        {
            level       (4 4);
            regions
            {
                diffuser { level (4 4); patchInfo { type wall; } }
            }
        }

'''
anchor = "        // The `diffuser` refinementSurface is INSERTED HERE"
assert anchor in s, "refinementSurfaces anchor missing"
s = s.replace(anchor, surf + anchor, 1)

anchor = "        // The `diffuser` layer entry is INSERTED HERE"
assert anchor in s, "layers anchor missing"
s = s.replace(anchor, "        diffuser { nSurfaceLayers 0; }\n\n" + anchor, 1)

open(p, "w").write(s)
PY
    grep -q "name        diffuser;" system/snappyHexMeshDict \
      && grep -q "diffuser { level (4 4)" system/snappyHexMeshDict \
      && grep -q "diffuser { nSurfaceLayers 0; }" system/snappyHexMeshDict \
      || { echo "failed to insert diffuser into snappyHexMeshDict" >&2 ; exit 1 ; }

    # The diffuser is a no-slip wall like any other, so it has to match the
    # 0.orig patch regexes. They are alternations, and a patch matching NONE of
    # them is a fatal "unable to find patchField" at solver start -- not a
    # silent default. Cheap to do, loud to get wrong.
    for f in 0.orig/U 0.orig/p 0.orig/k 0.orig/omega 0.orig/nut; do
        [ -f "$f" ] || continue
        sed -i 's/"(floor|walls|hood|tray)"/"(floor|walls|hood|tray|diffuser)"/' "$f"
    done
    grep -lq "hood|tray|diffuser" 0.orig/U \
      || { echo "failed to add diffuser to the 0.orig patch regexes" >&2 ; exit 1 ; }
    _sw=$(_geom DIFF_SWIRL)
    echo "  diffuser  $DIFF_TYPE, $(_geom DIFF_VANES) vanes at ${DIFF_TILT} deg, level 4, 0 layers"
    # Plain double quotes inside the single-quoted awk program. Backslash-escaped
    # quotes are literal backslashes to awk, not quoting, and it dies with
    # "runaway string constant" -- on stderr, while the surrounding echo still
    # prints, so the swirl line looked fine and the >0.6 WARNING never fired.
    if [ "$_sw" != none ]; then
        echo "            swirl number S = $_sw"
        awk -v s="$_sw" 'BEGIN{ if (s > 0.6) {
            print "  !! S > 0.6: expect vortex breakdown and a central"
            print "     recirculation bubble -- re-breathing in a closed box." } }'
    fi
else
    echo "  diffuser  none (control arm)"
fi

# --- jet shear-layer refinement (opt-in) ------------------------------------
# Adds the `jetShear` region at ONE LEVEL ABOVE inletJet. See snappyHexMeshDict
# for the geometry and for why this is opt-in rather than default.
#
# NOTE the anchor: this used to insert above `traySlotLeft`, which no longer
# exists. It now anchors on outletJet, the last surviving default region.
if [ "$JETREFINE" = 1 ]; then
    JETLEVEL=3
    sed -i "s|^        outletJet     { mode inside; levels ((1e15 2)); }|        outletJet     { mode inside; levels ((1e15 2)); }\n        jetShear      { mode inside; levels ((1e15 $JETLEVEL)); }|" \
        system/snappyHexMeshDict
    grep -q "jetShear      { mode inside" system/snappyHexMeshDict \
      || { echo "failed to enable jetShear refinement" >&2 ; exit 1 ; }
    echo "  jetRefine: jetShear region enabled at level $JETLEVEL (inlet shear layer)"
fi

# --- fan flow rate ----------------------------------------------------------
# Solve the fan curve against the system curve unless --Q overrode it. Bisection
# rather than anything cleverer: the residual is monotone in Q on [0, QFREE]
# (fan pressure falls, system loss rises), so 60 halvings is exact to machine
# precision and cannot fail to bracket.
# The vane cascade is part of the system curve too. K ~ 0.2 on the port dynamic
# head is the usual figure for well-formed turning vanes, i.e. ~0.8 Pa here
# against ~17 Pa of spare head -- so it costs about 1 % of Q, not enough to
# matter but wrong to omit. It does mean the diffused arms run at a marginally
# lower Q than the control, which is the physically honest comparison: a real
# diffuser does cost flow. The difference is far below the run-to-run noise.
if [ -n "$DIFF_TILT" ]; then
    KSYS=$(awk -v k="$KSYS" 'BEGIN{printf "%.3f", k + 0.2}')
fi

if [ -z "$Q_M3H" ]; then
    Q_M3H=$(awk -v qf="$FAN_QFREE" -v dp="$FAN_DPMAX" -v k="$KSYS" \
                -v rho="$RHO_AIR" -v a="$A_PORT" 'BEGIN{
        lo=0; hi=qf;
        for(i=0;i<60;i++){
            q=(lo+hi)/2;
            f=dp*(1-q/qf) - k*0.5*rho*(q/3600.0/a)^2;
            if(f>0) lo=q; else hi=q;
        }
        printf "%.3f", (lo+hi)/2;
    }')
    DP_OP=$(awk -v k="$KSYS" -v rho="$RHO_AIR" -v a="$A_PORT" -v q="$Q_M3H" \
        'BEGIN{printf "%.1f", k*0.5*rho*(q/3600.0/a)^2}')
    echo "  fan       Sunon MF50100V2 on Oe${PORT_D_MM} mm  ->  Q $Q_M3H m3/h at $DP_OP Pa"
    echo "            (solved from the fan curve; override with --Q)"
else
    DP_OP=$(awk -v k="$KSYS" -v rho="$RHO_AIR" -v a="$A_PORT" -v q="$Q_M3H" \
        'BEGIN{printf "%.1f", k*0.5*rho*(q/3600.0/a)^2}')
    DP_FAN=$(awk -v qf="$FAN_QFREE" -v dp="$FAN_DPMAX" -v q="$Q_M3H" \
        'BEGIN{printf "%.1f", dp*(1-q/qf)}')
    # A hand-set Q is a physical claim about the fan, so check it against the
    # curve instead of taking it on trust.
    awk -v s="$DP_OP" -v f="$DP_FAN" 'BEGIN{exit !(s > f + 0.5)}' && {
        echo "  !! Q = $Q_M3H m3/h needs $DP_OP Pa but the fan gives only $DP_FAN Pa there."
        echo "     This operating point is OFF the fan curve -- it is an assumption,"
        echo "     not a delivered flow. Drop --Q to solve for the real one."
    }
fi

Q_M3S=$(awk -v q="$Q_M3H" 'BEGIN{printf "%.6e", q/3600.0}')
U_IN=$(awk  -v q="$Q_M3S" -v a="$A_PORT" 'BEGIN{printf "%.4f", q/a}')
RE=$(awk    -v u="$U_IN" -v d="$PORT_D_MM" 'BEGIN{printf "%.0f", u*d/1000.0/1.516e-5}')
foamDictionary -entry "boundaryField/inlet/volumetricFlowRate" -set "$Q_M3S" 0.orig/U > /dev/null 2>&1

# tau is needed by the transient block below, so derive it here rather than
# down with the rest of the notes arithmetic.
ACH=$(awk -v q="$Q_M3H" -v v="$V_AIR" 'BEGIN{printf "%.0f", q/v}')
TAU=$(awk -v q="$Q_M3S" -v v="$V_AIR" 'BEGIN{printf "%.2f", v/q}')

# U_bulk is the scale the tray metric actually lives on, and at the new
# operating point it is the whole design story: the chamber CANNOT be
# over-ventilated (0.8 m/s in the bulk would need 35.9 m3/h), so the only way to
# exceed the ceiling anywhere is a surviving jet core, and the only way to reach
# 0.3 m/s everywhere is piston-like flow. A_free = 124.8 cm2 (CLAUDE.md 6.2).
U_BULK=$(awk -v q="$Q_M3S" 'BEGIN{printf "%.3f", q/1.248e-2}')

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
# Cell size at the port, in mm. The inlet/outlet are refinementSurfaces at
# level 2 (base/4), or level 3 with --jetRefine (base/8). Needed by BOTH the
# laminar shear-layer check below and the transient time-step cap, so it is
# computed here rather than inside the `laminar` block.
BASE_MM=$(awk -v n="$NX" 'BEGIN{printf "%.6f", 126.6667/n}')
DIV=$([ "$JETREFINE" = 1 ] && echo 8 || echo 4)
H_PORT_MM=$(awk -v b="$BASE_MM" -v d="$DIV" 'BEGIN{printf "%.6f", b/d}')

if [ "$MODEL" = laminar ]; then
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

    # --- writeInterval must scale with the flow, like endTime does -----------
    # Third constant found sized for a superseded operating point, after
    # maxDeltaT and the port area. A fixed 0.5 s was 96 frames when tau was
    # 7.29 s and is NINE frames at tau = 0.71 s -- enough to restart from,
    # nowhere near enough to animate. Derive it from a frame count instead, so
    # every run is animatable at every flow rate by construction.
    WRITE_INT=$(awk -v e="$END_TIME" -v n="$FRAMES" 'BEGIN{printf "%.6g", e/n}')
    sed -i "s/^writeInterval   0.5;/writeInterval   $WRITE_INT;/" system/controlDict
    grep -q "^writeInterval   $WRITE_INT;" system/controlDict \
      || { echo "failed to set writeInterval in system/controlDict" >&2 ; exit 1 ; }

    # purgeWrite 0 is the template default now, but assert it: the whole point
    # of this block is that a run cannot silently end up unanimatable, and a
    # stale template would do exactly that.
    grep -q "^purgeWrite      0;" system/controlDict \
      || { echo "system/controlDict does not have purgeWrite 0 -- frames would" >&2
           echo "be deleted as the run proceeds and CANNOT be recovered." >&2
           exit 1 ; }

    # --- project the disk cost, BEFORE the run ------------------------------
    # 271 bytes/cell/write measured 2026-08-16 on p1d_ctrl_m0 (382,613 cells,
    # kOmegaSST, binary, including the *Mean and _0 fields). Phase 2 adds T and
    # alphat: CLAUDE.md 3.3 measured that at +40 %.
    BPC=271 ; [ "$PHASE" = 2 ] && BPC=380
    # Background cells under-count the final mesh badly (snappy multiplies it),
    # so scale by the measured m0 ratio of final/background = 382613/12673 = 30.
    EST_CELLS=$(( NX * NY * NZ * 30 ))
    EST_GB=$(awk -v c="$EST_CELLS" -v b="$BPC" -v n="$FRAMES" \
        'BEGIN{printf "%.1f", c*b*n/1024/1024/1024}')
    FREE_GB=$(df -BG --output=avail "$ROOT" | tail -1 | tr -dc '0-9')
    echo "  frames    $FRAMES at writeInterval ${WRITE_INT}s, purgeWrite 0"
    echo "            projected ~${EST_GB} GB of time directories (${FREE_GB} GB free)"
    if awk -v e="$EST_GB" -v f="$FREE_GB" 'BEGIN{exit !(e > f*0.5)}'; then
        echo "  !! that is more than half the free disk. Lower --frames, or free"
        echo "     space, before running this. Frames cannot be recovered after"
        echo "     the fact, but disk exhaustion mid-run loses the whole case."
    fi

    sed -i "s/__AVG_START__/$AVG_START/" system/functions/transientMonitors
    # `if`, not `grep ... && { }` -- under `set -e` the latter's exit status is
    # the grep's, and a NOT-found placeholder (the success case) reads as failure.
    if grep -q "__AVG_START__" system/functions/transientMonitors; then
        echo "failed to set timeStart in functions/transientMonitors" >&2 ; exit 1
    fi

    # --- maxDeltaT must scale with the flow, like endTime does ---------------
    # MEASURED 2026-08-15. The template shipped a FIXED maxDeltaT 1e-3, chosen
    # for Q = 5 m3/h. At Q = 1.25 that cap binds long before maxCo does -- the
    # m0+jetRefine run sat at max Courant 2.03 against a limit of 6 -- so the
    # step size stayed at the Q = 5 value while endTime grew 4x with tau. The
    # run therefore cost 4x MORE than at Q = 5, not less.
    #
    # That is also where CLAUDE.md 5.1's "2.3 h at 1.25 m3/h vs 9.1 h at 5"
    # went wrong: it applied the dt ~ 1/U saving but not the endTime ~ 1/Q
    # penalty. The two CANCEL EXACTLY. At a fixed jet Courant number a 6.6-tau
    # transient is the same number of steps at every Q:
    #
    #     steps = 6.6 * tau / dt,   tau ~ 1/Q,   dt ~ 1/U ~ 1/Q   =>  constant
    #
    # So set the cap on the quantity that actually matters -- the Courant number
    # in the JET, on the port cell -- rather than on the clock:
    #
    #     maxDeltaT = JET_CO * h_port / U_in
    #
    # JET_CO 2.6 is not a new number: it is the value the template's own
    # measured anchor already used (Q = 5, m1, h_port 0.833 mm, dt 4.9e-4 s),
    # and this expression reproduces that 4.9e-4 exactly. maxCo 6 stays as the
    # safety net for the small near-wall cells.
    JET_CO=2.6
    MAXDT=$(awk -v c="$JET_CO" -v h="$H_PORT_MM" -v u="$U_IN" \
        'BEGIN{printf "%.4g", c*h/1000/u}')
    sed -i "s/^maxDeltaT       1e-3;/maxDeltaT       $MAXDT;/" system/controlDict
    grep -q "^maxDeltaT       $MAXDT;" system/controlDict \
      || { echo "failed to set maxDeltaT in system/controlDict" >&2 ; exit 1 ; }

    NSTEPS=$(awk -v e="$END_TIME" -v d="$MAXDT" 'BEGIN{printf "%.0f", e/d}')
    # Compute the tau multiple rather than echoing N_TAU_END: with --endTime the
    # two differ, and printing the constant would report a 0.03-tau smoke test as
    # a 6.6-tau production run.
    NT_END=$(awk -v e="$END_TIME" -v t="$TAU" 'BEGIN{printf "%.2f", e/t}')
    NT_AVG=$(awk -v a="$AVG_START" -v t="$TAU" 'BEGIN{printf "%.2f", a/t}')
    echo "  transient: endTime $END_TIME s ($NT_END tau), avgStart $AVG_START s ($NT_AVG tau),"\
         "maxDeltaT $MAXDT s -> ~$NSTEPS steps"
    if awk -v n="$NT_END" 'BEGIN{exit !(n < 4)}'; then
        echo "  !! only $NT_END tau of simulated time. A start-from-rest field needs"
        echo "     ~3 flow-throughs to forget its initial condition, so anything"
        echo "     below ~4 tau is a SMOKE TEST, not a result. Statistics from it"
        echo "     are meaningless -- do not report them."
    fi
    echo "     (jet Courant $JET_CO on the ${H_PORT_MM} mm port cell at $U_IN m/s;"
    echo "      step count is ~independent of Q -- dt ~ 1/Q and endTime ~ 1/Q cancel)"

elif [ -n "$END_TIME" ]; then
    # Steady: "time" is the SIMPLE iteration count. Capping it is only ever for
    # a smoke test -- a steady run at any Q on this geometry does not converge
    # (CLAUDE.md 5.1), so a short one proves the dicts load and the solver
    # starts, nothing more.
    sed -i "s/^endTime         4000;/endTime         $END_TIME;/" system/controlDict
    grep -q "^endTime         $END_TIME;" system/controlDict \
      || { echo "failed to set endTime in system/controlDict" >&2 ; exit 1 ; }
    echo "  steady: endTime capped at $END_TIME iterations (default 4000)"
    if awk -v e="$END_TIME" 'BEGIN{exit !(e < 500)}'; then
        echo "  !! $END_TIME iterations is a SMOKE TEST, not a result. It proves the"
        echo "     dicts load and the solver starts. Nothing more -- and a steady"
        echo "     run here does not converge at 4000 either (CLAUDE.md 5.1)."
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
if [ "$PHASE" = 2 ]; then
    echo "  LED        $LED W  ->  predicted bulk dT $DT K"

    # --- thermal viability, BEFORE any CFD is spent on it --------------------
    # Steady state, adiabatic walls, all LED power to air: the ventilation
    # stream is the only heat sink, so P = mdot*cp*dT. dT is therefore fixed by
    # P and Q ALONE -- no mesh, no turbulence model and no amount of mixing
    # changes it (CLAUDE.md 6.3). CFD decides UNIFORMITY; the mean is already
    # determined here. So say so at generation time rather than after a run.
    #
    # ⚠ The two working defaults COMPOUND, and CLAUDE.md 6.3's table hides it:
    # that table was computed at Q = 5 m3/h and reports dT = 22.9 K for 38.4 W.
    # The working Q is now 1.25 m3/h (CLAUDE.md 10.2), and dT scales as 1/Q, so
    # the DEFAULT pair 38.4 W + 1.25 m3/h gives dT = 91.7 K -- a 111 C chamber,
    # four times worse than the figure the doc quotes, and ~30x the 3 K that
    # keeps microgreens in their 22-25 C band.
    TIN=20                      # inlet air, CLAUDE.md 6.3 placeholder [C]
    TOUT=$(awk -v t="$TIN" -v d="$DT" 'BEGIN{printf "%.0f", t + d}')
    PMAX=$(awk -v q="$Q_M3S" 'BEGIN{printf "%.1f", 3.0*(q*1.2*1004.5)}')
    if awk -v d="$DT" 'BEGIN{exit !(d > 5)}'; then
        echo "  !! THERMALLY NON-VIABLE: dT = $DT K puts the chamber at ~$TOUT C"
        echo "     against a 22-25 C target. This is an ENERGY BALANCE, not a CFD"
        echo "     result -- P = mdot*cp*dT with the vent stream as the only sink."
        echo "     No mesh, model or mixing improvement changes it."
        echo "     At Q = $Q_M3H m3/h the ceiling is about ${PMAX} W for a 3 K rise."
        echo "     Run it to characterise FLOW STRUCTURE and STRATIFICATION only."
        echo "     Absolute temperatures from this case are NOT a prediction of the"
        echo "     built chamber -- say so in NOTES.md and on every figure axis."
    fi
fi
echo
echo "  cd runs/$NAME && ./Allrun"
