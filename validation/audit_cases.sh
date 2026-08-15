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
# NOT a substitute for regenerating. If a case is stale, the correct fix is
# `rm -rf runs/<case>` and generate it again (CLAUDE.md 1.3); this only tells
# you which ones need it.
#
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STALE=0
printf "%-30s %-19s %-11s %-11s %s\n" "case" "application" "maxDeltaT" "expected" "verdict"
printf "%s\n" "----------------------------------------------------------------------------------------"

for d in runs/*/; do
    c=$(basename "$d")
    cdict="$d/system/controlDict"
    [ -f "$cdict" ] || continue

    app=$(grep -oP '^application\s+\K\w+' "$cdict" 2>/dev/null)
    [ -n "$app" ] || continue

    mdt=$(grep -oP '^maxDeltaT\s+\K[0-9.eE+-]+' "$cdict" 2>/dev/null)
    if [ -z "$mdt" ]; then
        printf "%-30s %-19s %-11s %-11s %s\n" "$c" "$app" "-" "-" "steady - n/a"
        continue
    fi

    q=$(awk '/volumetricFlowRate/{gsub(";","",$2); print $2; exit}' "$d/0.orig/U" 2>/dev/null)
    nx=$(grep -oP '^nx\s+\K[0-9]+' "$d/system/blockMeshDict" 2>/dev/null)
    if [ -z "$q" ] || [ -z "$nx" ]; then
        printf "%-30s %-19s %-11s %-11s %s\n" "$c" "$app" "$mdt" "?" "cannot determine"
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

    want=$(awk -v n="$nx" -v dv="$div" -v q="$q" \
        'BEGIN{u=q/3.14159265e-4; h=126.6667/n/dv/1000; printf "%.4g", 2.6*h/u}')
    ok=$(awk -v a="$mdt" -v b="$want" 'BEGIN{r=a/b; print (r>0.98 && r<1.02)?"OK":"STALE"}')
    [ "$ok" = STALE ] && STALE=$((STALE + 1))

    printf "%-30s %-19s %-11s %-11s %s\n" "$c" "$app" "$mdt" "$want" "$ok"
done

echo
if [ "$STALE" -gt 0 ]; then
    echo "$STALE case(s) STALE. They will still run, and will still produce"
    echo "plausible output -- with the wrong time step. Regenerate them:"
    echo "    rm -rf runs/<case> && scripts/generate_case.sh --name <case> ..."
    exit 1
fi
echo "all transient cases agree with the current generator."
