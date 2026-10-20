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

## Changelog

Do not edit `CHANGELOG.md` in a pull request. Add a fragment instead, so
parallel pull requests do not conflict:

    changelog.d/<pull request number>.<type>.md

with `<type>` one of `added`, `enabled` (a feature flag switched on),
`changed`, `fixed`, `limitation`, and one entry in Markdown (or several as
`- ` items) as the content. When the number is not known yet, use a short
kebab-case topic (`changelog.d/string-agg.added.md`); a topic gets no
`(#<number>)` reference. Details in [changelog.d/README.md](changelog.d/README.md);
`python scripts/assemble_changelog.py check` validates the fragments (the
offline tier runs the same check) and `draft` shows the resulting section.

## pub400 tests

Tests that write to the IBM i use the tests.testapp tables: a module asks for
them with `pytestmark = pytest.mark.usefixtures("testapp_tables")`
(`tests/pub400/conftest.py`), which creates the tables for that module and
drops them again. Put a test in the module of its area (`test_schema.py`,
`test_queries.py`, `test_aggregates.py`, ...).

Run sessions that connect to PUB400 from the host with `scripts/pub400.sh`
(`scripts/pub400.sh pub400`, `scripts/pub400.sh probe <name>`). It is
`docker compose run --rm tests nox -s <session>`, wrapped in `caffeinate` on
macOS: a Mac that sleeps during a long run breaks the connection (08S01,
CWBCO1034). `scripts/runtests.sh` goes through it too.

## Golden files

`tests/offline/golden/<django>/<profile>/<group>/<name>.sql` hold the SQL the
backend generates for a fixed set of cases (`tests/golden_cases/`), per
Django series and capability profile. The offline tier compares the generated
SQL and params with them on every run.

- **Where cases live:** one module per group, `tests/golden_cases/<group>.py`
  (ddl, queries, values, expressions, aggregates, extract, dml, flush), with
  the shared builders in `base.py`. A case named `<group>/<name>` goes into
  its group's module; the offline tier checks this.

- **Scope:** backend-specific SQL only (pagination, quoting, booleans,
  date/time parameters, LIKE escaping, identity handling, flush, DDL types).
  Do not add SQL that Django generates the same way for every backend.
- **Changing SQL on purpose:** run `pytest -m offline --update-goldens`, review
  the diff and commit it with the code change. Never in CI (refused there).
- **Verification status** (`-- verified:` header): `unverified`, or
  `<level>, <date>` with the level `IBM i <release> on PUB400 (TR <n>, Db2 PTF
  Group <n>), Django <version>` (TR and PTF Group are `unknown` where they
  cannot be read, as on PUB400). **"Verified" means "accepted by Db2 for
  i"** (the statement executed without an error), **not** "returns correct
  results"; correct results are what the Django test runs check. Any change to
  a golden's SQL **or** params resets it to `unverified`.
- **Verifying:** `nox -s pub400 -- -k goldens --record-verification` executes
  every golden on IBM i (create goldens first, in an empty marked test library).
  A golden that passed is stamped only when it was unverified or verified on
  another level (release, TR, PTF Group or Django version); a run on the same
  level leaves the goldens alone and only writes its date and counts to
  `tests/offline/golden/last-verification.txt`. Commit the changes in a PR.
  Goldens that Db2 for i rejects are listed in `tests/pub400/test_goldens.py`
  (`REJECTED`) with the reason until the backend is fixed.
- **Completeness:** every case has a golden and every golden has a case;
  `depends:` names the create goldens a golden needs, so it is skipped (with
  the reason) when one of them fails on IBM i.
- **No system names:** goldens must not contain library or user profile names;
  the verification header names only the release and "PUB400".

## Running Django's own test suite

On a shared system such as PUB400 only single, small modules run, never the
full suite:

```sh
scripts/runtests.sh 6.1 basic              # reuse the test library (--keepdb)
scripts/runtests.sh 6.1 --clean basic      # fully clean run
scripts/runtests.sh 6.1 --clean --debug-sql basic.tests.ModelTest.test_x
                                           # rerun a failing label: log its SQL
docker compose run --rm tests nox -s test_status   # regenerate docs/TEST_STATUS.md
```

- Needs a checkout of Django in `vendor/django-<version>` on
  `stable/<version>.x` (gitignored); the script tells you how to clone it.
- Settings: `tests/django_settings/settings_runtests_pub400.py`; `default` and
  `other` are the two journaled libraries from `.env`
  (`DB2I_DEFAULT_LIBRARY`, `DB2I_OTHER_LIBRARY`), each guarded by the test
  marker table. `other` connects only when a selected test uses it.
- `--debug-sql` passes Django's `runtests.py --debug-sql`: the log shows the
  SQL of each failing test with its parameter values, so the exact failing
  statement is visible. The password is scrubbed from all output, as always;
  the SQL never contains the connection string.
- The scripts refuse runs without modules or with more than three, always
  use `--parallel=1 --noinput`, and write one log per module to
  `test-results/<version>/<module>.log`, with the password scrubbed.
- With `--keepdb` the marker table records the module; running another
  module drops the previous module's tables first, so tables do not pile up in
  the library.
- Known failures go into `DatabaseFeatures.expected_failures` /
  `django_test_skips` under one of the fixed `REASON_*` strings.

## Offline query corpus

Statements that passing Django tests sent to Db2 for i become offline
regression checks (design: `docs/proposals/offline-query-corpus.md`):

```sh
scripts/runtests.sh 6.1 --clean --capture ordering     # PUB400: record the passing tests' statements
docker compose run --rm tests sh -c 'uv run --no-project --python 3.14 python scripts/build_corpus.py 6.1'
docker compose run --rm tests nox -s "corpus(3.14-django6.1)"   # replay offline, no IBM i
```

- `--capture` writes `test-results/<version>/corpus/<label>.jsonl`; only tests
  that passed count (`tests/corpus/capture.py`).
- `scripts/build_corpus.py` turns the captures into
  `tests/offline/corpus/<django>/<profile>/` (gzip JSONL per module, a plain SQL
  index for review, a manifest with the Django commit). Build a module only
  from captures of all of its labels; unchanged modules stay byte-identical.
- `nox -s corpus` installs Django from exactly the manifest's commit (library
  and test suite) and compares the SQL and params the backend writes now. A
  mismatch means "no longer the SQL that passed on IBM i"; `--update-corpus`
  (never in CI) rewrites it and clears the stamp. CI runs it as a step of each
  offline job.

## Releases

Releases are alpha releases on GitHub only (no PyPI). **Contributors and
Claude never create release tags; the maintainer creates and signs them.**

0. **Release run**, for every supported Django version (newest Python), one
   after another: `docker compose run --rm tests nox -s release_run -- <django>`.
   It checks that PUB400's database port answers (otherwise it stops at
   once), runs every supported Django test module (the `[[modules]]` of
   `docs/status.toml`, `queries` as its labels), each with `--clean` in its own
   run, then the pub400 tier with `--create-db`; logs in
   `test-results/<django>/`. Report the results in the release PR.
1. **Release PR** (prepared like any other PR): set `__version__` in
   `django_db2_for_i/__init__.py` (the single source of the version) and run
   `python scripts/assemble_changelog.py release <version>`: it writes the
   fragments in `changelog.d/` into a `## [<version>] - <date>` section of
   `CHANGELOG.md`, updates the comparison links at the bottom and deletes the
   fragments. Review the section and commit it with the deletions. The
   offline tier checks that `__version__` has a CHANGELOG section.
2. **The maintainer merges it** and tags the merge commit on `main` from
   their own release clone, signed with their OpenPGP (GPG) key:

   ```sh
   git switch main && git pull --ff-only
   git log -1 --show-signature          # the merge commit of the release PR
   git tag -s v<version> -m "v<version>"
   git tag -v v<version>                # check the signature locally
   git push origin v<version>
   ```

   The tag must be annotated (`-s` makes a signed, annotated tag), signed
   with the key whose public part is stored ASCII-armored in the admin-only
   Actions variable `RELEASE_SIGNING_KEY`, point to a commit on `main`, and
   equal `v` + `__version__`.
3. **The release workflow** (`.github/workflows/release.yml`) verifies all of
   that (`scripts/verify_release_tag.py`), builds the sdist and wheel, runs
   the offline tier against the installed wheel (`nox -s wheel`) and creates
   a GitHub **pre-release** with both files and the version's CHANGELOG
   section (`scripts/changelog_section.py`). If any check fails, nothing is
   published; fix the cause, delete the tag (`git push --delete origin
   v<version>`, `git tag -d v<version>`) and tag again.

Published tags are never moved or recreated. `v0.1.0a1` predates this
workflow and its code reports version `0.0.1.dev0` (see `CHANGELOG.md`).
