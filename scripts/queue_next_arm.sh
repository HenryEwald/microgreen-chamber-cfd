#!/bin/bash
#
# Launch the third transient arm once the first one frees its cores.
#
#   nohup scripts/queue_next_arm.sh > /tmp/queue_next_arm.log 2>&1 &
#
# Written 2026-08-15 to survive the session that created it. The three arms do
# not fit on 16 physical cores at once (8 + 8 + 4), so `p1_trans_q1p25_m0_lam`
# waits for `..._m0_lam_jet` to finish and then takes cores 0-3. That chaining
# was originally an interactive background job, which would have died with its
# session and silently left the third arm unrun -- the queue would simply never
# have fired, with nothing in any log to say so.
#
# What the third arm is for: it is the plain-m0 control (no --jetRefine, so the
# inlet shear layer is unresolved anywhere in the domain, x_res = 202 mm > the
# 186.7 mm path). Comparing its unsteadiness against the refined arm answers
# whether --jetRefine buys unsteadiness fidelity or only jet-spreading accuracy
# -- see validation/transient_matrix.md 4c. It costs 12,270 steps against the
# refined arm's 24,546, because the coarser port cell doubles the time step at
# fixed jet Courant.
#
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

WAIT_FOR=${WAIT_FOR:-p1_trans_q1p25_m0_lam_jet}
LAUNCH=${LAUNCH:-p1_trans_q1p25_m0_lam}
CPUSET=${CPUSET:-0-3}

echo "$(date -Is)  waiting for $WAIT_FOR to finish, then launching $LAUNCH on cores $CPUSET"

# Poll the predecessor's Allrun output rather than its PID: Allrun prints
# `== done` only after the solve AND reconstructPar have completed cleanly, and
# `did NOT finish` if the solver died. A PID check cannot tell those apart.
while true; do
    out="$ROOT/runs/$WAIT_FOR/allrun.out"
    if [ -f "$out" ]; then
        if grep -q "^== done" "$out"; then
            echo "$(date -Is)  $WAIT_FOR finished cleanly"
            break
        fi
        if grep -qE "did NOT finish|checkMesh FAILED" "$out"; then
            echo "$(date -Is)  !! $WAIT_FOR FAILED -- not launching $LAUNCH."
            echo "   Investigate runs/$WAIT_FOR before starting anything else;"
            echo "   a failure there probably affects $LAUNCH too."
            exit 1
        fi
    fi
    sleep 300
done

if [ -f "$ROOT/runs/$LAUNCH/log.pimpleFoam" ]; then
    echo "$(date -Is)  $LAUNCH already has log.pimpleFoam -- nothing to do."
    exit 0
fi

echo "$(date -Is)  launching $LAUNCH"
cd "$ROOT/runs/$LAUNCH" || exit 1
FOAM_CPUSET="$CPUSET" ./Allrun > allrun.out 2>&1
status=$?
echo "$(date -Is)  $LAUNCH Allrun exited $status"
tail -5 allrun.out
