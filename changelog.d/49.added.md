README badges (supported versions, license, offline CI, latest release, and
the passed / failed / skipped / expected-failure counts of the last Django
test runs on PUB400) with an explanation of what they mean, and a "Project
status" section (releases, phases, phase 2 modules, open tracks).
`scripts/update_test_status.py` (`nox -s test_status`) now also writes the
shields.io endpoint files in `docs/badges/` and renders the README status
between marker comments from `docs/status.toml` and the test logs.
