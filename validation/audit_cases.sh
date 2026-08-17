#!/bin/bash
#
# Do the cases in runs/ still agree with what the CURRENT generator would make?
#
#   validation/audit_cases.sh
#
# Cases in runs/ are disposable but they PERSIST, and templates/ and
# scripts/generate_case.sh keep changing. A case generated before a template fix
# carries the old value silently -- it still meshes, still solves, still writes
# plausible output. This checks the settings where that drift would be invisible
# and expensive.
#
# Currently checked:
#
#   maxDeltaT   Must be 2.6 * h_port / U_in -- a fixed jet Courant number on the
#               port cell. Before 2026-08-15 this was a hard-coded 1e-3 sized
#               for Q = 5 m3/h; at Q = 1.25 that binds long before maxCo does
#               and the run costs 4x more (CLAUDE.md 5.1). Nothing in the log
#               says so -- max Courant just sits at 2.03 against a limit of 6.
#
#   geometry    The case's own constant/triSurface/tray.stl, byte-compared with
#               what scripts/make_geometry.py produces TODAY. Added 2026-08-16,
#               when the tray went flush with all four walls: V_air moved 2.530
#               -> 2.3296 L and the tray metric area 0.014375 -> 0.0224 m2, so
#               every pre-existing case answers a question about a DIFFERENT
#               CHAMBER. Nothing in a log says that either -- the old cases mesh
#               cleanly, solve fine, and report a tray mean that looks entirely
#               reasonable next to the new one.
#
#               Only checkable on cases that have been RUN: generate_case.sh
#               leaves triSurface/ empty and Allrun fills it. Unrun cases report
#               "-" and are fine by construction.
#
# NOT a substitute for regenerating. If a case is stale, the correct fix is
# `rm -rf runs/<case>` and generate it again (CLAUDE.md 1.3); this only tells
# you which ones need it.
#
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STALE=0
GEOMSTALE=0

# Reference geometry, generated fresh from the CURRENT script. Byte-comparison
# is the right test here: make_geometry.py is deterministic and fully analytic
# (CLAUDE.md 7), so identical parameters give an identical file. Any diff at all
# is a real geometry change, not float noise.
REF=$(mktemp -d)
trap 'rm -rf "$REF"' EXIT

# EXTENDED 2026-08-16 to compare chamber.stl as well as tray.stl, and to
# regenerate against the CASE'S OWN geometry arguments.
#
# tray.stl alone was sufficient only while the chamber shape was a constant. It
# is not any more: --portD changes the end walls and the port opening, and it
# leaves tray.stl BYTE-IDENTICAL. A Oe 20 case audited against a Oe 40 generator
# would therefore have reported geometry OK while describing a different
# chamber -- the exact failure mode this check exists to catch, reintroduced by
# making the geometry parametric.
#
# A case with no system/geometryArgs predates the parametric port entirely, so
# it is stale by definition rather than by comparison.
ref_geom() {  # ref_geom <args...> -> populates $REF, echoes the triSurface dir
    rm -rf "$REF/constant"
    # shellcheck disable=SC2086
    python3 scripts/make_geometry.py --case "$REF" $1 > "$REF/log" 2>&1 || return 1
    echo "$REF/constant/triSurface"
}

printf "%-30s %-19s %-11s %-11s %-9s %s\n" \
    "case" "application" "maxDeltaT" "expected" "geometry" "verdict"
printf "%s\n" "-------------------------------------------------------------------------------------------------"

for d in runs/*/; do
    c=$(basename "$d")
    cdict="$d/system/controlDict"
    [ -f "$cdict" ] || continue

    app=$(grep -oP '^application\s+\K\w+' "$cdict" 2>/dev/null)
    [ -n "$app" ] || continue

    # Geometry: independent of steady/transient, so evaluate it for every case.
    casetray="$d/constant/triSurface/tray.stl"
    casecham="$d/constant/triSurface/chamber.stl"
    if [ ! -f "$casetray" ] || [ ! -f "$casecham" ]; then
        geom="-"                     # never run: Allrun fills triSurface/
    elif [ ! -f "$d/system/geometryArgs" ]; then
        # No recorded arguments => generated before the port became a parameter,
        # i.e. a Oe 20 chamber. Nothing to compare against; it is simply old.
        geom="STALE"
        GEOMSTALE=$((GEOMSTALE + 1))
    else
        read -r gargs < "$d/system/geometryArgs"
        if refdir=$(ref_geom "$gargs"); then
            if cmp -s "$refdir/tray.stl" "$casetray" \
            && cmp -s "$refdir/chamber.stl" "$casecham"; then
                geom="OK"
            else
                geom="STALE"
                GEOMSTALE=$((GEOMSTALE + 1))
            fi
        else
            geom="?"                 # generator refused these arguments
        fi
    fi

    mdt=$(grep -oP '^maxDeltaT\s+\K[0-9.eE+-]+' "$cdict" 2>/dev/null)
    if [ -z "$mdt" ]; then
        printf "%-30s %-19s %-11s %-11s %-9s %s\n" \
            "$c" "$app" "-" "-" "$geom" "steady - n/a"
        continue
    fi

    q=$(awk '/volumetricFlowRate/{gsub(";","",$2); print $2; exit}' "$d/0.orig/U" 2>/dev/null)
    nx=$(grep -oP '^nx\s+\K[0-9]+' "$d/system/blockMeshDict" 2>/dev/null)
    if [ -z "$q" ] || [ -z "$nx" ]; then
        printf "%-30s %-19s %-11s %-11s %-9s %s\n" \
            "$c" "$app" "$mdt" "?" "$geom" "cannot determine"
        continue
    fi

    # ⚠ Detect --jetRefine by the refinementRegions ENTRY, not by the string
    # "jetShear". The searchableBox that defines the region is present in EVERY
    # case; only the `jetShear { mode inside; ... }` line under
    # refinementRegions is added by --jetRefine. Grepping the bare name reports
    # every case as refined and silently halves the expected maxDeltaT -- which
    # this script did on its first draft, flagging three correct cases as stale.
    if grep -q "jetShear  *{ *mode inside" "$d/system/snappyHexMeshDict" 2>/dev/null; then
        div=8
    else
        div=4
    fi

    # Port area, from the case's OWN geometry rather than a constant. This was
    # a hard-coded 3.14159265e-4 (Oe 20) until 2026-08-16, which flagged every
    # correctly-generated Oe 40 case as STALE by a factor of 4 -- the audit
    # carrying exactly the duplicated constant it exists to police.
    aport=$(awk '$1=="PORT_AREA"{print $2}' \
        "$d/constant/triSurface/geometry.info" 2>/dev/null)
    [ -n "$aport" ] || aport=3.14159265e-4     # pre-parametric cases were Oe 20

    want=$(awk -v n="$nx" -v dv="$div" -v q="$q" -v a="$aport" \
        'BEGIN{u=q/a; h=126.6667/n/dv/1000; printf "%.4g", 2.6*h/u}')
    ok=$(awk -v a="$mdt" -v b="$want" 'BEGIN{r=a/b; print (r>0.98 && r<1.02)?"OK":"STALE"}')
    [ "$ok" = STALE ] && STALE=$((STALE + 1))

    printf "%-30s %-19s %-11s %-11s %-9s %s\n" \
        "$c" "$app" "$mdt" "$want" "$geom" "$ok"
done

echo
if [ "$GEOMSTALE" -gt 0 ]; then
    echo "$GEOMSTALE case(s) have STALE GEOMETRY -- their tray.stl differs from what"
    echo "scripts/make_geometry.py produces now. These are not slightly-off runs;"
    echo "they describe a DIFFERENT CHAMBER, with a different V_air, a different tau"
    echo "and a different tray metric area (CLAUDE.md 6.1). Their results remain"
    echo "valid answers about the geometry they were run on -- do NOT silently"
    echo "compare them against new cases, and do not delete them if they are"
    echo "referenced by anything in validation/."
    echo
fi
if [ "$STALE" -gt 0 ]; then
    echo "$STALE case(s) STALE on maxDeltaT. They will still run, and will still"
    echo "produce plausible output -- with the wrong time step. Regenerate them:"
    echo "    rm -rf runs/<case> && scripts/generate_case.sh --name <case> ..."
fi
if [ "$STALE" -gt 0 ] || [ "$GEOMSTALE" -gt 0 ]; then
    exit 1
fi
echo "all cases agree with the current generator, geometry included."
