#!/bin/sh
# Run modules of Django's own test suite against IBM i, in the tests container.
#
#   scripts/runtests.sh <django-version> [--clean] <module> [<module> ...]
#   scripts/runtests.sh 6.1 basic transactions
#
# One runtests.py call per module (--parallel=1 --noinput, --keepdb unless
# --clean), logs in test-results/<version>/<module>.log with the password
# scrubbed. Refuses to run without modules (the full suite) or with more than
# three modules: the system is shared (CLAUDE.md, PUB400 rules).
# The checks are repeated inside the container (scripts/run_django_tests.py).
set -eu

usage() {
    echo "usage: $0 <django-version> [--clean] <module> [<module> ...]" >&2
    exit 2
}

[ $# -ge 1 ] || usage
version=$1
shift
modules=0
for arg in "$@"; do
    case $arg in
        --clean) ;;
        -*) echo "refused: unknown option $arg" >&2; exit 2 ;;
        *) modules=$((modules + 1)) ;;
    esac
done
if [ "$modules" -eq 0 ]; then
    echo "refused: name the test modules; the full Django test suite never runs on a shared system" >&2
    exit 2
fi
if [ "$modules" -gt 3 ]; then
    echo "refused: at most 3 modules per run on a shared system" >&2
    exit 2
fi

cd "$(dirname "$0")/.."
exec docker compose run --rm tests nox -s django_tests -- "$version" "$@"
