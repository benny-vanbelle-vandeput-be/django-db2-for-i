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

The routine tasks have scripts in `bin/`, run from the host. Each has `--help`
and `--dry-run` (print the commands, run nothing), and none prints secrets.
The workflow, step by step, is in [docs/WORKFLOW.md](docs/WORKFLOW.md)
(`bin/help`, `bin/help <topic>`).

| Script | What it does |
|---|---|
| `bin/help` | the workflow guide: the quick start and the topics (`bin/help <topic>`) |
| `bin/setup` | first-time setup: images, `.env` (asked in your own terminal), `vendor/` checkouts |
| `bin/doctor` | checks the environment, then one connection to PUB400 |
| `bin/check` | what CI does, locally: lint, offline tests, corpus replay, gate, classification |
| `bin/verify` | verifies changed SQL and new tests on IBM i and writes the stamps |
| `bin/ibmi-test` | chosen own IBM i tests, Django test labels, `--affected` or `--full-tier` on IBM i |
| `bin/probe` | IBM i probes by name: `qtemp_` probes (read-only or QTEMP; the ones with their own entry point by file name, e.g. `bin/probe qtemp_encoding`); `lib_` probes only with `--approved <link>` to the maintainer's approval; `--publish` puts a result into the repository |
| `bin/status` | regenerates the status pages; shows the PUB400 lock and labelled pull requests |
| `bin/ibmi-cleanup` | lists (`--yes`: drops) the leftover test tables of a crashed run |
| `bin/status-run` | the status run on IBM i, per Django version, resumable |
| `bin/release-prepare` | checks the release preconditions and opens the release pull request |
| `bin/worktree-remove` | removes a merged worktree, keeping its test results in the main checkout |

`bin/setup` is for humans in their own terminal: it asks for the `.env`
values (the password hidden) and writes them with mode 600; an existing
`.env` is never read or changed. Claude never runs it interactively and never
enters values, only without a terminal (then `.env` is just the template) or
when `.env` exists. `bin/verify` stops before PUB400 when an offline failure
is not changed SQL, never commits, and its report
(`test-results/verify/<django>/report.txt`) says plainly when new SQL was
written but not verified; more than 60 Django test labels or 20 runs are
refused (`--max-labels`, `--max-runs`). `bin/ibmi-cleanup` works under the
standing approval in CLAUDE.md: only objects on the list that test runs
write before each `CREATE`, only in a library with the `DJDB2I_TEST_MARKER`
table; it lists only, unless `--yes`.

The IBM i scripts take `--wait` to queue behind a running PUB400 job.

Every run against PUB400 goes through `scripts/pub400.sh`, which holds the
PUB400 lock: one PUB400 job at a time on the machine. A second job stops with
"PUB400 busy: <holder>", or waits with `scripts/pub400.sh --wait ...`.

### Pinned tooling

The dev and test tooling (pytest, pytest-django, ruff and what they need) is
pinned in `uv.lock`; the nox sessions install exactly those versions, so a new
release never changes `bin/check` or CI by itself. `pyproject.toml` keeps
open ranges in `[dependency-groups]`. The library's runtime dependencies are
not pinned: the sessions install the newest Django patch release of each
supported version and the newest pyodbc, the versions users get.

- Dependabot (`.github/dependabot.yml`) proposes updates as one weekly pull
  request, for releases at least 7 days old; the maintainer merges it like any
  other. A lock update is "docs/tests only": offline CI checks it, no IBM i run.
- By hand: `docker compose run --rm tests uv lock --upgrade-package <name>`;
  after changing `[dependency-groups]`, `uv lock` (the sessions refuse a lock
  that does not match `pyproject.toml`).

## Test sets

Four test sets, named the same everywhere, code included (README,
TEST_STATUS, this file, CLAUDE.md):

| Test set | What and where | Was |
|---|---|---|
| Offline tests | this project's unit tests and golden SQL checks, `tests/offline/`, `nox -s offline`; CI on every commit | offline tier |
| IBM i tests | this project's tests against a real Db2 for i, `tests/ibmi/`, `nox -s ibmi`; when the pull request's classification asks for it | pub400 tier |
| Django suite on IBM i | Django's own test modules against Db2 for i, `scripts/django_suite.sh`; before every release (the status run) | Django modules on PUB400 |
| Replay tests | the recorded SQL of passing Django tests (the corpus), compiled again offline, `nox -s replay`; CI on every commit | offline query corpus |

Each run of the nox sessions writes its counts to
`test-results/<django>/sets/` (`--results-summary`); `nox -s test_status`
turns them, with the Django test logs, into README's "Test status".

## Pull requests and IBM i runs

Every pull request is classified from its changed files
(`scripts/classify_pr.py`; run it yourself with
`python scripts/classify_pr.py --base origin/main`). The CI job `classify`
runs it on every push, keeps one comment on the pull request up to date and
adds the labels; for a pull request from a fork it only writes the job
summary.

| Class | What changed | IBM i run | Label |
|---|---|---|---|
| needs full IBM i run | `django_db2_for_i/drivers/`, `base.py`, `creation.py`, `capabilities.py`, the core backend (`schema.py`, `introspection.py`, `compiler.py`, `operations.py`, `features.py`, `expressions.py`, `compat.py`), the container image (`docker/`, `compose.yaml`), the pinned Django commit, the supported Django versions, and any path the script does not list | the full own IBM i tests | `needs-full-ibmi-run` |
| SQL-affecting | other backend code; goldens or corpus entries without a verification stamp | the affected tests | `run-ibmi` |
| docs/tests only | the paths the script lists as such | only for changes that run on IBM i (own IBM i tests, test models, IBM i settings, the IBM i run tooling such as `scripts/pub400.sh`, the nox sessions, the supported Django test modules) | `run-ibmi` for those |

- The script fails closed: a new file or directory is "needs full IBM i run" until
  it is added to the script's lists, in the same pull request (an offline test
  checks that every tracked file is listed).
- Anyone may add `run-ibmi` by hand to request a run.
- The labels are removed only after the run on the pull request's latest
  commit has passed and its result (the commit, the counts) is posted on the
  pull request. A pull request with either label is not merged.
- The status `ibmi-gate` checks the same independently of the labels: it is
  red while an IBM i run is needed and no posted result covers the pull
  request's current content. A result comment starts with
  `<!-- ibmi-run sha=<full sha> tier=targeted|full -->` and counts only from
  the machine account or the maintainer (`scripts/ibmi_gate.py`).
- A later push brings the labels back, except a push that only adds the
  verification stamps written by the run (and files generated from them), a
  push whose own files are docs/tests that do not run on IBM i (such as a
  renamed changelog fragment), and a conflict-free rebase whose own changes are identical (`git range-diff`)
  onto docs/tests-only commits of `main` (or commits that change only the IBM
  i gate: `.github/workflows/ibmi-gate.yml`, `scripts/ibmi_gate.py` and
  `scripts/classify_pr.py`), also when it carries the run's verification
  stamps commit along.
- Pull requests are rebased onto `main` whenever they are behind it (the
  `main` ruleset requires the `offline` check on an up-to-date branch).

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
Offline tests run the same check) and `draft` shows the resulting section.

## IBM i tests (`tests/ibmi/`)

Tests that write to the IBM i use the tests.testapp tables: a module asks for
them with `pytestmark = pytest.mark.usefixtures("testapp_tables")`
(`tests/ibmi/conftest.py`), which creates the tables for that module and
drops them again. It works in a marked library (`tests/ibmi/marked_library.py`):
the `DJDB2I_TEST_MARKER` table is written first, so `bin/ibmi-cleanup` can drop
what a crashed module left, and teardown leaves the library without tables,
marker included. Put a test in the module of its area (`test_schema.py`,
`test_queries.py`, `test_aggregates.py`, ...).

Run sessions that connect to PUB400 from the host with `scripts/pub400.sh`
(`scripts/pub400.sh ibmi`, `scripts/pub400.sh probe <name>`). It is
`docker compose run --rm tests nox -s <session>`, wrapped in `caffeinate` on
macOS: a Mac that sleeps during a long run breaks the connection (08S01,
CWBCO1034). `scripts/django_suite.sh` goes through it too.

## Golden files

`tests/offline/golden/<django>/<profile>/<group>/<name>.sql` hold the SQL the
backend generates for a fixed set of cases (`tests/golden_cases/`), per
Django series and capability profile. The Offline tests compare the generated
SQL and params with them on every run.

- **Where cases live:** one module per group, `tests/golden_cases/<group>.py`
  (ddl, queries, values, expressions, aggregates, extract, dml, flush), with
  the shared builders in `base.py`. A case named `<group>/<name>` goes into
  its group's module; the Offline tests check this.

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
- **Verifying:** `nox -s ibmi -- -k goldens --record-verification` executes
  every golden on IBM i (create goldens first, in an empty marked test library).
  A golden that passed is stamped only when it was unverified or verified on
  another level (release, TR, PTF Group or Django version); a run on the same
  level leaves the goldens alone and only writes its date and counts to
  `tests/offline/golden/last-verification.txt`. Commit the changes in a PR.
- **The verification gate** (`nox -s gate`, run by CI as part of the
  required `offline` check): every golden and every corpus entry must carry a
  verification stamp. A pull request with new or changed SQL stays red until
  the stamps of its IBM i run are committed. The gate is not part of
  `nox -s offline`, so the pull request can be pushed before its run.
- **Unverifiable goldens:** goldens that cannot be verified on the test
  system are listed in `tests/offline/golden/unverifiable.toml`, each with its
  reason and the condition under which it becomes verifiable (for example "a
  dedicated IBM i with a CPA32B2 system reply list entry"). The gate accepts
  them, the IBM i golden check expects them to fail, and TEST_STATUS shows
  their count. An entry that is no longer needed (the golden is verified or
  gone) fails the gate.
- **Completeness:** every case has a golden and every golden has a case;
  `depends:` names the create goldens a golden needs, so it is skipped (with
  the reason) when one of them fails on IBM i.
- **No system names:** goldens must not contain library or user profile names;
  the verification header names only the release and "PUB400".

## Django suite on IBM i (Django's own tests)

On a shared system such as PUB400 only single, small modules run, never the
full suite:

```sh
scripts/django_suite.sh 6.1 basic              # reuse the test library (--keepdb)
scripts/django_suite.sh 6.1 --clean basic      # fully clean run
scripts/django_suite.sh 6.1 --clean --debug-sql basic.tests.ModelTest.test_x
                                           # rerun a failing label: log its SQL
docker compose run --rm tests nox -s test_status   # regenerate docs/TEST_STATUS.md
```

- Needs a checkout of Django in `vendor/django-<version>` on
  `stable/<version>.x` (gitignored); the script tells you how to clone it.
- Settings: `tests/django_settings/settings_django_suite.py`; `default` and
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

## Replay tests

Statements that passing Django tests sent to Db2 for i become offline
regression checks: the test set "Replay tests",
reference in [docs/REPLAY_TESTS.md](docs/REPLAY_TESTS.md):

```sh
scripts/django_suite.sh 6.1 --clean --capture ordering     # PUB400: record the passing tests' statements
docker compose run --rm tests sh -c 'uv run --no-project --python 3.14 python scripts/build_corpus.py 6.1'
docker compose run --rm tests nox -s "replay(3.14-django6.1)"   # replay offline, no IBM i
```

- `--capture` writes `test-results/<version>/corpus/<label>.jsonl`; only tests
  that passed count (`tests/corpus/capture.py`).
- `scripts/build_corpus.py` turns the captures into
  `tests/offline/replay/<django>/<profile>/` (gzip JSONL per module, a plain SQL
  index for review, a manifest with the Django commit). Build a module only
  from captures of all of its labels; unchanged modules stay byte-identical.
- `nox -s replay` installs Django from exactly the manifest's commit (library
  and test suite) and compares the SQL and params the backend writes now. A
  mismatch means "no longer the SQL that passed on IBM i"; `--update-corpus`
  (never in CI) rewrites it and clears the stamp. CI runs it as a step of each
  offline job.

## Releases

Releases are alpha releases on GitHub only (no PyPI). **Contributors and
Claude never create release tags; the maintainer creates and signs them.**

0. **Status run**, for every supported Django version (newest Python):
   `bin/status-run` (all versions, one after another) or
   `bin/status-run --django <version>`. Per version, under the PUB400 lock,
   it checks that PUB400's database port answers (otherwise it stops at
   once), runs every supported Django test module (the `[[modules]]` of
   `docs/status.toml`, `queries` as its labels), each with `--clean` and
   `--capture` in its own run, then the IBM i tests with `--create-db`; logs in
   `test-results/<django>/`, raw corpus captures in
   `test-results/<django>/corpus/`. It is **resumable**: each result is
   recorded at once (`test-results/<django>/status-run/state.json`), and a
   later start on the same backend and Django commits skips what passed, so
   the run can be spread over several nights (`--restart` starts over,
   `--limit N` stops after N runs). When every run of a version passed, it
   rebuilds that version's corpus
   ([REPLAY_TESTS.md](docs/REPLAY_TESTS.md)) in the working tree.
1. **Release PR**: `bin/release-prepare <version>` in the main checkout (not a
   subagent worktree). It refuses unless HEAD is `origin/main` with only the
   status runs' corpus changed, CI passed on `main`, the verification gate
   passes, the version is newer than `__version__`, there are changelog
   fragments, and every supported Django version has a complete, passed
   status run with the backend unchanged since. Then it commits the corpus,
   sets `__version__` in `django_db2_for_i/__init__.py` (the single source of
   the version), runs `python scripts/assemble_changelog.py release <version>`
   (the fragments in `changelog.d/` become a `## [<version>] - <date>` section
   of `CHANGELOG.md`, the comparison links are updated and the fragments
   deleted), regenerates the status pages and FEATURES.md, runs `bin/check`,
   pushes `chore/release-<version>` and opens the pull request with the
   status runs and corpus counts. It never tags and never creates releases;
   it ends by printing the steps below.
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
3. **Create the GitHub release yourself** (the release workflow is parked,
   see #94).

Published tags are never moved or recreated. `v0.1.0a1` predates this
workflow and its code reports version `0.0.1.dev0` (see `CHANGELOG.md`).
