#!/bin/sh
# Run modules of Django's own test suite against IBM i, in the tests container.
#
#   scripts/runtests.sh <django-version> [--clean] <label> [<label> ...]
#   scripts/runtests.sh 6.1 basic transactions
#   scripts/runtests.sh 6.1 basic.tests.ModelTest.test_x
#
# A label is a test module or a dotted label inside one. One runtests.py call
# per label (--parallel=1 --noinput, --keepdb unless --clean), logs in
# test-results/<version>/<module>.log (dotted labels: labels/<label>.log) with
# the password scrubbed. Refuses to run without labels (the full suite) or
# with more than three labels: the system is shared (CLAUDE.md, PUB400 rules).
# The checks are repeated inside the container (scripts/run_django_tests.py).
set -eu

usage() {
    echo "usage: $0 <django-version> [--clean] <label> [<label> ...]" >&2
    exit 2
}

[ $# -ge 1 ] || usage
version=$1
shift
labels=0
for arg in "$@"; do
    case $arg in
        --clean) ;;
        -*) echo "refused: unknown option $arg" >&2; exit 2 ;;
        *) labels=$((labels + 1)) ;;
    esac
done
if [ "$labels" -eq 0 ]; then
    echo "refused: name the test modules; the full Django test suite never runs on a shared system" >&2
    exit 2
fi
if [ "$labels" -gt 3 ]; then
    echo "refused: at most 3 labels per run on a shared system" >&2
    exit 2
fi

cd "$(dirname "$0")/.."
exec docker compose run --rm tests nox -s django_tests -- "$version" "$@"
