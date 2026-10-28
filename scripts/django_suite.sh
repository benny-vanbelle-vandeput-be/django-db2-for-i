#!/bin/sh
# Run modules of Django's own test suite against IBM i, in the tests container.
#
#   scripts/django_suite.sh <django-version> [--clean] [--debug-sql] [--capture] <label> [<label> ...]
#   scripts/django_suite.sh 6.1 basic transactions
#   scripts/django_suite.sh 6.1 basic.tests.ModelTest.test_x
#   scripts/django_suite.sh 6.1 --clean --debug-sql basic.tests.ModelTest.test_x
#
# A label is a test module or a dotted label inside one. One runtests.py call
# per label (--parallel=1 --noinput, --keepdb unless --clean), logs in
# test-results/<version>/<module>.log (dotted labels: labels/<label>.log) with
# the password scrubbed. --debug-sql passes runtests.py's --debug-sql: the
# log shows the SQL of each failing test (with its parameter values, scrubbed
# like the rest of the output), for rerunning failing labels. --capture records
# the statements of passing tests for the offline query corpus
# (test-results/<version>/corpus/<label>.jsonl; scripts/build_corpus.py). Refuses to run without labels (the full suite) or
# with more than three labels: the system is shared (CLAUDE.md, PUB400 rules).
#
# The rules live in one place, scripts/run_django_tests.py (#204): it checks
# the arguments here, with the host's python3 (standard library only), before
# the PUB400 lock is taken, and again inside the container.
set -eu

python3 "$(dirname "$0")/run_django_tests.py" --check-only "$@"

# Through scripts/pub400.sh: on macOS, the Mac does not sleep during the run.
exec "$(dirname "$0")/pub400.sh" django_suite "$@"
