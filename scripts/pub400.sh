#!/bin/sh
# Run a nox session that connects to PUB400, from the host, in the tests container:
#
#   scripts/pub400.sh <session> [<arg> ...]
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
set -eu

if [ $# -lt 1 ]; then
    echo "usage: $0 <nox-session> [<arg> ...]" >&2
    exit 2
fi
session=$1
shift
case $session in
    pub400|django_tests|release_run|probe|probe_*) ;;
    *)
        echo "refused: $session does not connect to PUB400; run: docker compose run --rm tests nox -s $session" >&2
        exit 2
        ;;
esac

cd "$(dirname "$0")/.."
set -- docker compose run --rm tests nox -s "$session" -- "$@"
if command -v caffeinate >/dev/null 2>&1; then
    set -- caffeinate -i -s "$@"
fi
exec "$@"
