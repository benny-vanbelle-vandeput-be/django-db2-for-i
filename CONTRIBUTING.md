# Contributing

Thank you for your interest in django-db2-for-i.

## License of contributions

This project is licensed under the [BSD 3-Clause License](LICENSE), the same
license as Django. By submitting a contribution (pull request, patch, or any
other form), you agree that it is licensed under the same BSD 3-Clause License.

- Code or tests adapted from Django keep their original copyright notice.
- Do not submit code copied from projects with an incompatible license.
- The IBM i Access ODBC Driver is not part of this project and must never be
  committed or redistributed.

## Ground rules

- No credentials in commits, logs, or issue reports. Connection settings come
  from environment variables or a local `.env` file (gitignored).
- One logical change per commit, with a
  [Conventional Commits](https://www.conventionalcommits.org/) message
  (`feat:`, `fix:`, `docs:`, `test:`, `build:`, `ci:`, `chore:`).
- Claims about IBM i behaviour must be backed by a probe script in `probes/`
  and a note in `docs/IBMI_NOTES.md`.
- Every test skip or expected failure carries a one-line reason.
- Never run the full Django test suite against PUB400 or any other shared system.

## Development environment

All development and test runs happen in a container. See [README.md](README.md)
for setup instructions.

## Golden files

`tests/offline/golden/<django>/<profile>/<group>/<name>.sql` hold the SQL the
backend generates for a fixed set of cases (`tests/golden_cases.py`), per
Django series and capability profile. The offline tier compares the generated
SQL and params with them on every run.

- **Scope:** backend-specific SQL only (pagination, quoting, booleans,
  date/time parameters, LIKE escaping, identity handling, flush, DDL types).
  Do not add SQL that Django generates the same way for every backend.
- **Changing SQL on purpose:** run `pytest -m offline --update-goldens`, review
  the diff and commit it with the code change. Never in CI (refused there).
- **Verification status** (`-- verified:` header): `unverified`, or
  `IBM i <release> on PUB400, <date>`. **"Verified" means "accepted by Db2 for
  i"** (the statement executed without an error), **not** "returns correct
  results"; correct results are what the Django test runs check. Any change to
  a golden's SQL **or** params resets it to `unverified`.
- **Verifying:** `nox -s pub400 -- -k goldens --record-verification` executes
  every golden on IBM i (create goldens first, in an empty marked test library)
  and stamps those that were accepted. Commit the header changes in a PR.
  Goldens that Db2 for i rejects are listed in `tests/pub400/test_goldens.py`
  (`REJECTED`) with the reason until the backend is fixed.
- **Completeness:** every case has a golden and every golden has a case;
  `depends:` names the create goldens a golden needs, so it is skipped (with
  the reason) when one of them fails on IBM i.
- **No system names:** goldens must not contain library or user profile names;
  the verification header names only the release and "PUB400".
