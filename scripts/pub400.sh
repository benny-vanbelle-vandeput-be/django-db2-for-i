#!/bin/sh
# Run a nox session that connects to PUB400, from the host, in the tests container:
#
#   scripts/pub400.sh [--wait] <session> [<arg> ...]
#   scripts/pub400.sh pub400
#   scripts/pub400.sh pub400 -k goldens --record-verification
#   scripts/pub400.sh probe constraint_errors
#   scripts/pub400.sh release_run 6.1
#
# On macOS the run is wrapped in caffeinate (no idle or system sleep while it
# runs): a Mac that sleeps during a long run breaks the TLS connection, and
# the run fails with 08S01 "Communication link failure" (CWBCO1034). Only
# sessions that connect to PUB400 are accepted; scripts/runtests.sh uses this
# script for django_tests.
#
# Every run holds the PUB400 lock (scripts/pub400_lock.py, outside every
# checkout): one PUB400 job at a time on this machine, whatever the worktree.
# A second run stops with "PUB400 busy: <holder>", or waits with --wait (or
# DB2I_LOCK_WAIT=1, which also reaches runs started by scripts/runtests.sh).
# The lock is released only after the run's container is gone: when the run
# is stopped, the lock stops the container first (docker stop, then kill).
set -eu

wait=
if [ "${DB2I_LOCK_WAIT:-}" = 1 ]; then
    wait=--wait
fi
if [ "${1:-}" = --wait ]; then
    wait=--wait
    shift
fi
if [ $# -lt 1 ]; then
    echo "usage: $0 [--wait] <nox-session> [<arg> ...]" >&2
    exit 2
fi
session=$1
shift
case $session in
    pub400|django_tests|release_run|probe|probe_*|ibmi_cleanup) ;;
    *)
        echo "refused: $session does not connect to PUB400; run: docker compose run --rm tests nox -s $session" >&2
        exit 2
        ;;
esac

cd "$(dirname "$0")/.."
# Read on the host: in a git worktree the container cannot read the repository.
commit=$(git log -1 --format='%h %cs' 2>/dev/null || echo unknown)
# The state directory of the lock, outside every checkout, also holds the list
# of objects test runs create (tests/table_registry.py, bin/ibmi-cleanup).
state=$(python3 scripts/pub400_lock.py --dir)
mkdir -p "$state"
# A named container: the lock stops it before it is released (a stopped run
# would otherwise leave the container and its PUB400 connection behind).
container="db2i-pub400-$$"
set -- docker compose run --rm --name "$container" -e DB2I_BACKEND_COMMIT="$commit" \
    -v "$state:/db2i-state" -e DB2I_TABLE_LIST=/db2i-state/created-objects.txt \
    tests nox -s "$session" -- "$@"
if command -v caffeinate >/dev/null 2>&1; then
    set -- caffeinate -i -s "$@"
fi
exec python3 scripts/pub400_lock.py $wait --container "$container" -- "$@"
