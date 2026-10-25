# django-db2-for-i — Django database backend for Db2 for IBM i

## 1. Goal

Build, from scratch, a Django database backend for **Db2 for IBM i** (AS/400, iSeries).

- Start with a **minimal working backend** with almost all optional features **disabled**.
- Enable features **one at a time**, driven by Django's own test suite.
- Do not copy code from existing backends (`ibm_db_django`, django-pyodbc variants, mssql-django).
  You may read them for reference on IBM i quirks and backend patterns.
- Usage for end users: `DATABASES = {"default": {"ENGINE": "django_db2_for_i", ...}}`.

### License
- **BSD-3-Clause**, the same license as Django. Copyright holder: **Benny Van Belle**.
  `LICENSE` line: `Copyright (c) 2026, Benny Van Belle`. Use the same name as `authors` in `pyproject.toml`.
- `LICENSE` file in the repo root; `pyproject.toml` uses `license = "BSD-3-Clause"`
  (SPDX expression) and `license-files = ["LICENSE"]`.
- `CONTRIBUTING.md` states that contributions are accepted under the same license.
- Code or tests adapted from Django (BSD-3-Clause) keep their copyright notice.
- Never copy code from projects with incompatible licenses. The IBM i Access ODBC Driver is
  not part of this project and is never redistributed.

## 2. Working rules (read first)

- **Plan before code.** For every phase: propose a plan, wait for approval, then implement.
- **Small, reviewable commits.** One logical change per commit; conventional commit messages.
- **Never guess IBM i behaviour.** When uncertain, write a tiny probe script in `probes/`,
  run it against the test system, and record the finding in `docs/IBMI_NOTES.md`.
- **Never mark a test as skipped / expected failure without a reason** (one line, in the list itself).
- **No credentials in the repo or the image.** Use environment variables / `.env` (gitignored).
  Never read, print, log or echo `.env` or its values; scripts load it themselves.
  Error messages and logs must never contain the password or full connection string.
- **`bin/setup` is for humans in their own terminal.** It asks for the `.env` values;
  Claude never runs it interactively and never enters values. Claude runs it only
  without a terminal (then `.env` is just a copy of `.env.example`) or when `.env`
  already exists.
- **Respect shared systems.** Never run the full Django suite against PUB400 or any shared system
  (see "Initial test system: PUB400" for what is allowed).
- Record non-obvious design decisions in `docs/DECISIONS.md` (date, decision, why, alternatives).
- **IBM i runs follow the PR's classification** (`scripts/classify_pr.py`, see "Git
  workflow"), and the result is reported in the PR:
  - a **targeted run** (the affected own IBM i tests and Django test modules or ids)
    for new or changed tests that run on IBM i, for changed SQL (a golden or corpus
    entry without a verification stamp) and on request;
  - the **full** pub400 tier (`nox -s pub400`), not a subset, when the driver layer,
    `base.py`, `creation.py`, the capabilities, the container image, the pinned Django
    commit or the supported Django versions change, or a file the classification does
    not list (it fails closed);
  - nothing for docs/tests-only changes that do not run on IBM i.
- When a feature flag is enabled, add an own pub400 test for the common real-world usage
  pattern of that feature (e.g. full querysets with model instances, not only `values()`);
  Django's own tests do not cover every pattern.
- At the end of each phase: update `docs/TEST_STATUS.md`, add changelog fragments, commit,
  and summarize what was done and what comes next.
- At every module or phase transition (a module or phase starts or is done, a release,
  an open track added or closed): update `docs/status.toml` and regenerate
  `docs/TEST_STATUS.md`, `docs/badges/*.json` and README's status section with
  `nox -s test_status`. Never edit the generated parts of README.md by hand.
- All code, comments and docs in English.

## 3. Supported versions

### Django
- Supported now: **Django 5.2 LTS, 6.0 and 6.1**. Not 4.2.
- Policy: follow Django's own support table. A version stays supported until it reaches
  end of life (end of security support), then it is dropped in the first release of this
  backend after that date (6.0 included).
  When **6.2 LTS** ships it is added alongside the versions still supported.
- Develop phases 0–2 against **6.1 only**. Add 6.0 and 5.2 support after phase 2 (phase 3).
- For each supported version, read the **"Database backend API"** section of the Django
  release notes and record the impact in `docs/DJANGO_VERSIONS.md`.

### Python
- Python **3.12, 3.13, 3.14** — verify per Django version in its release notes
  (including the minimum 6.0.x and 5.2.x patch releases that support 3.14).

### IBM i
- Minimum and primary target: **IBM i 7.5**. 7.4 may be added later on request; the
  capabilities layer must make that possible without touching backend logic.
- Features may depend on the IBM i release *and* on the Technology Refresh / Db2 PTF Group level.

### Initial test system: PUB400
Development starts on **PUB400** (public community IBM i, 7.5) until a dedicated system is available.
- Each user has **two pre-existing libraries**, one for `default` and one for `other`.
  The phase 0 probe discovers them (libraries owned by the current user), and the user
  confirms which is which before they go into `.env`.
  The user cannot create schemas, so `creation.py` needs the "use existing schema" mode
  from **phase 1** on (not phase 7).
- Commitment control requires journaled tables. Libraries created with CRTLIB are not
  journaled automatically: verify in phase 0 whether a `QSQJRN` journal exists in both
  libraries, and record the result in `docs/IBMI_NOTES.md`.
- **Probes are read-only by default.** Anything that changes the IBM i (e.g. creating a
  journal receiver and `QSQJRN` journal) is proposed first and only run after approval.
  - **Exception: QTEMP.** Probes may create and change objects in `QTEMP` without
    approval: QTEMP is job-scoped, private to the probe's own connection, and
    everything in it vanishes when the job ends.
  - Nothing outside QTEMP (a library, a table in a user library, a journal, a
    system value, a reply list entry) may be created or changed without approval.
  - **A probe's name says where it acts**: `probes/qtemp_<topic>.py` only
    reads, or writes only in QTEMP (or its own job); `probes/lib_<topic>.py`
    creates or changes anything outside QTEMP. A probe whose scope grows beyond
    QTEMP becomes a `lib_` probe before it runs. Every probe report states where
    it ran (read-only, QTEMP, or which library and which objects).
  - **No `lib_` probe without the maintainer's explicit approval for that
    specific probe, and the approval is a link.** Before any `lib_` probe,
    Claude asks first, saying what it creates or changes and how it cleans up,
    and waits for an approval **comment by the maintainer on GitHub** (an
    answer in the session is not enough). It covers only that probe as
    described; more or other objects need a new approval. It is enforced:
    `bin/probe --approved <comment link> lib_<topic>` checks on GitHub that the
    comment is the maintainer's (`scripts/probe_approval.py`), the nox session
    `probe_lib` is the only way a `lib_` probe starts, `probes/_common.connect()`
    refuses a `lib_` probe without the approval, and the link is stored with
    the result. This holds for its dry run too. `tests/offline/test_probes.py`
    checks the names and the gate.
  - **Standing approval (2026-10-21): `bin/ibmi-cleanup`** (phase 4 step 0) may drop
    leftover test tables, with their indexes and views, in the two `.env` libraries,
    and nothing else: only tables on the local list that test runs write *before*
    each `CREATE TABLE` (`tests/table_registry.py`, in the state directory next to the
    PUB400 lock), only in a library that contains the `DJDB2I_TEST_MARKER`
    table, never a table of the marker's snapshot, never a library, journal,
    receiver or system object. Without `--yes` it only lists; it writes what it
    dropped to `test-results/cleanup/`. A table not on the list is reported, and
    dropping it needs approval.
    **Renames (extended 2026-10-24):** a `RENAME TABLE` by a test run updates the
    entry of a table that is already on the list (the same entry, never a new
    object). *Before* the statement runs, the entry holds the new name and the old
    one (`renamed_from`); if it fails, the entry as it was again; a rename back
    updates it the same way, so the list holds the current name.
    **In a transaction (amended 2026-10-24, item 11a, `can_rollback_ddl`):** the
    pending entry (both names, or every name since the last commit) is cleared
    only after the transaction commits (`on_commit`); in autocommit /
    `atomic = False` it is cleared after the statement succeeds. After a
    rollback, also of a savepoint, the entry keeps every name. After a crash or
    a rollback `bin/ibmi-cleanup` drops whichever of the names exists. A table
    not on the list is never added by a rename. The marker rule above is
    unchanged.
- PUB400 limits connections per IP: one connection per run, `--parallel=1`, no retry storms.
- **One PUB400 job at a time on this machine**, whatever the worktree: no probe, tier
  or Django run starts while another one runs; it queues instead. `scripts/pub400.sh`
  enforces this with a per-user lock outside every checkout
  (`scripts/pub400_lock.py`: `~/.local/state/django-db2-for-i/pub400.lock`, an OS file
  lock released when the process dies; "PUB400 busy: <holder>", or `--wait`;
  `bin/status` shows the holder). Every PUB400 run goes through `scripts/pub400.sh`.
  It covers one machine only: two machines behind the same IP are not covered.
- No uptime guarantee: test runs must fail fast and clearly when the system is unreachable.
- Allowed on PUB400: single, small Django test modules (e.g. `basic`, `transactions`) and the
  curated `pub400` tier. **Never** the full Django suite or the full matrix.
- Connect with pyodbc + IBM i Access ODBC Driver (database host server port 8471, 9471 for TLS).

## 4. Architecture: three independent axes

| Axis | Question | Location |
|---|---|---|
| Django version | Which backend API does Django expect? | `django_db2_for_i/compat.py` |
| Driver | How do we talk to the server? | `django_db2_for_i/drivers/` |
| Server | What can this Db2 for i do? | `django_db2_for_i/capabilities.py` |

Rules:
- No `django.VERSION` checks outside `compat.py`. Write it so adding or dropping a Django
  version is a local change (one place to delete 5.2 code later).
- No IBM i version checks outside `capabilities.py`.
- No driver-specific code outside `drivers/`. The driver layer knows nothing about Django.

### Driver layer (`django_db2_for_i/drivers/`)
- Small interface in `drivers/base.py`: connect, cursor, error mapping, type conversion.
- First implementation: **pyodbc** + IBM i Access ODBC Driver (`drivers/pyodbc.py`).
- Possible later implementations: Mapepire, `ibm_db` (e.g. for Python running in PASE on IBM i).
- Connection defaults (SQL naming, commitment control, CCSID) live here and are documented.

### Server capabilities (`django_db2_for_i/capabilities.py`)
- A `ServerCapabilities` object with booleans such as `has_boolean_type`,
  `has_limit_offset`, `has_json_functions`.
- Built once per connection: OS release from the driver (e.g. pyodbc `getinfo(SQL_DBMS_VER)`),
  plus targeted probes where a feature depends on TR / Db2 PTF Group level. Results are cached.
- Can be fully defined via `OPTIONS` (named profiles like `"7.5"`, later `"7.6"` or TR-specific ones, plus per-capability
  overrides). Required for the offline test tier.
- `features.py`, `operations.py`, `schema.py` only ask capabilities, never compare versions.

### Backend modules (`django_db2_for_i/`)
Standard Django backend layout: `base.py`, `features.py`, `operations.py`, `schema.py`,
`introspection.py`, `creation.py`, `client.py`, `compiler.py` (if needed), `validation.py`.

## 5. Feature strategy

- `features.py` starts **conservative**: every optional `DatabaseFeatures` flag that Django
  allows to be `False` is `False`.
- Use `django_test_skips` and `django_test_expected_failures` to mark known failures,
  with a short reason per entry. Build them per Django version where needed.
  **Shrinking these lists is the measure of progress.**
- Each enabled feature comes with: the flag change, the implementation, the related Django
  tests passing, offline tests, a regenerated `docs/FEATURES.md` (`nox -s features`; one-line
  description in `docs/features.toml`), and a changelog fragment (`changelog.d/`, see
  CONTRIBUTING.md).

### Known IBM i specifics to handle deliberately
- No `RETURNING`: use `SELECT ... FROM FINAL TABLE (INSERT ...)` for returning columns.
- `BOOLEAN` is available from 7.5 (our minimum); keep it behind a capability anyway
  (`SMALLINT` + `CHECK` would be the fallback if 7.4 is ever added).
- No timezone-aware timestamp type (`USE_TZ` handling in `operations.py`).
- Identifier case folding (uppercase), long SQL names vs 10-character system names,
  maximum identifier length.
- Pagination: `OFFSET` / `FETCH FIRST` vs `LIMIT`, depending on capabilities.
- CCSID / encoding (avoid CCSID 65535 problems).
- Commitment control and isolation levels (schemas created with `CREATE SCHEMA` get a
  journal, which commitment control requires).

## 6. Test tiers

Three tiers, selectable via pytest markers / nox sessions.

**Test set names.** README, TEST_STATUS, CONTRIBUTING and this file use four
user-facing names. Code (nox sessions, `tests/pub400/`, markers, the
`needs-full-tier` label) keeps the old names until one mechanical rename PR,
made when no other PRs are open.

| Test set | Old name |
|---|---|
| Offline · own tests | offline tier (`nox -s offline`) |
| IBM i · own tests | pub400 tier (`nox -s pub400`) |
| IBM i · Django test suite | Django modules on PUB400 (`scripts/runtests.sh`, `release_run`) |
| Offline · Django test suite (replay) | offline query corpus (`nox -s corpus`) |

### Tier 1 — `offline` = "Offline · own tests" (no IBM i needed; every commit, in CI)
- Compile querysets with `query.get_compiler(using).as_sql()` and compare SQL + params
  to golden files in `tests/offline/golden/`.
- Collect DDL with `connection.schema_editor(collect_sql=True)` for model and migration operations.
- Unit-test pure `DatabaseOperations` methods.
- Run for every capability profile (initially only 7.5).
- Each golden file records whether it has been **verified** against a real IBM i
  (version + date). Unverified goldens are listed in a report. The verification gate
  (`nox -s gate`, part of the required `offline` check in CI, not of the local offline
  tier) fails on any golden or corpus entry without a stamp, except the allow-listed
  goldens in `tests/offline/golden/unverifiable.toml` (reason and condition per entry).
- The `DatabaseWrapper` must never open a connection in this tier; a fixture fails loudly if it tries.
- CI never connects to PUB400 or any IBM i: it runs only lint and the offline tier, as
  parallel jobs (one per Python × Django combination). The aggregating `offline` job stays
  a required check on `main`.

### Tier 2 — `pub400` = "IBM i · own tests" (small curated smoke set for a shared, restricted system)
- Works in **pre-existing libraries**: `creation.py` supports a "use existing schema,
  never CREATE/DROP SCHEMA" mode and cleans up its own tables.
- Multi-database tests are skipped if no second library is configured.
- Includes a job that executes all golden-file SQL to verify it.
- Keep the load light. Check PUB400's terms of use and ODBC availability.

### Tier 3 — `full` = "IBM i · Django test suite" (Django's `runtests.py` against a dedicated IBM i)
- Source of truth for feature flags and `docs/TEST_STATUS.md`.
- Django checkouts in `vendor/django-<version>` (gitignored), on the `stable/<version>.x` branch.
- Settings in `tests/django_settings/settings_full.py`: `default` + `other` databases
  as two schemas with names of at most 10 characters (e.g. `DJTEST` and `DJTESTOTH`),
  configured via `.env`. Only used once a dedicated IBM i is available.
- `scripts/runtests.sh <django-version> <module...>` runs `runtests.py` with `--settings`,
  `--parallel=1`, saving output to `test-results/<django-version>/<module>.log`.
- `scripts/update_test_status.py` parses the logs and updates `docs/TEST_STATUS.md`:
  per test module the pass/fail/skip/xfail counts per Django version, date of the last run,
  and the enabled feature flags.
- Day-to-day: single modules against the primary version (6.1).
- Before every release: one run of all Django test modules we support (the modules in
  `docs/TEST_STATUS.md`) plus our own pub400 tier, for every supported Django version,
  newest Python. Sequential, one connection at a time, preferably off-peak. Never the full
  Django suite. The release run stays complete, but may be spread over several nights:
  it is resumable per Django version. During development: single modules/labels, and
  IBM i runs as the PR's classification requires (section 2).

### Version matrix
- offline: every Python × every Django version.
- pub400: one combination (newest Python, newest Django) during development; every
  supported Django version (newest Python) in the release run.
- full: newest Python × every Django version, plus oldest Python × newest Django.

## 7. Containerized environment

- All development and test runs happen in a container; the host only needs Docker or Podman.
- Provide `docker/Dockerfile`, `compose.yaml` and `.devcontainer/` so Claude Code can run
  inside the same environment.
- The image contains: IBM i Access ODBC Driver for Linux (installed from IBM's repository
  during build), unixODBC, `uv` with Python 3.12 / 3.13 / 3.14, `nox`.
- The ODBC driver is subject to IBM's license: the image is built locally / in private CI and
  **never pushed to a public registry**. Document this in `README.md`.
- Check whether an arm64 build of the ODBC driver exists; otherwise document running with
  `--platform linux/amd64`. Provide an image variant (build target) without the ODBC driver
  for the offline tier.
- Connection settings via environment variables / `.env` (gitignored, with `.env.example`).
- Volumes: `test-results/`, `vendor/` and a `uv` cache.
- One entry point: `docker compose run --rm tests nox -s <session>`.
- nox uses the `uv` backend to select Python versions.

## Documentation
- User documentation lives in `docs/user/` (installation, ODBC driver setup,
  DATABASES/OPTIONS reference, IBM i requirements such as journaling and
  authorities, known limitations, troubleshooting by SQLCODE).
- Developer documentation stays in `docs/` (DECISIONS, IBMI_NOTES, TEST_STATUS,
  DJANGO_VERSIONS).
- Any change to user-visible behaviour, settings or limitations updates
  `docs/user/` in the same commit.
- The GitHub wiki is a generated mirror of `docs/user/`, synced by a GitHub
  Action on pushes to main. Never edit the wiki directly.

## Git workflow
- Claude works on GitHub only as the machine account `claude-v-belle-net`
  (`GH_TOKEN`), never with the maintainer's account. This repository's local git
  config uses `gh auth git-credential` for pushes, so the keychain is not used.
- `main` is protected by a ruleset: changes only through pull requests with one
  approval by the maintainer, the `offline` check passing on an up-to-date
  branch, merge commits only (no rebase or squash merging), signed commits
  required. Never push to `main` directly and never force-push it.
- Every commit on `main` must be signed: the PR commits by the machine
  account's signing key, the merge commit by GitHub. Rebase merging is not
  used because it recreates the commits without signatures.
- One branch per logical change, named `<type>/<topic>` (`feat/`, `fix/`,
  `docs/`, `test/`, `ci/`, `chore/`), created from the current `origin/main`.
- **`.env` in worktrees:** a new worktree has no `.env` (gitignored). Link it
  (`ln -s ../django-db2-for-i/.env .env`, never reading it) only into worktrees the
  main session uses for IBM i runs. **Never** link or copy it into a subagent's
  worktree (`.claude/worktrees/`): subagents are offline only, and a missing `.env`
  is an extra safeguard there.
- **Results never vanish with a worktree.** Remove a merged worktree with
  `bin/worktree-remove <path>`: it copies its `test-results/` to the main checkout's
  `test-results/archive/<worktree>/` first. Raw probe output that a decision rests on
  goes into the repository with `bin/probe --publish <result>` (`probes/results/<probe>.json`,
  host, user and library names replaced, no credentials).
- Commits: conventional messages; author is the maintainer (noreply address),
  committer is the machine account (noreply address), every commit and tag is
  signed with the machine account's SSH signing key (all set in the
  repository's local git config). Never commit with a personal email address.
- Before every push: `nox -s lint offline` passes locally (`bin/check` runs it, with the
  corpus replay, the verification gate and the classification).
- **Every PR is classified** from its changed files by `scripts/classify_pr.py`:
  **needs full tier** (the driver layer, `base.py`, `creation.py`, the capabilities, the
  container image, the pinned Django commit, the supported Django versions, and every
  path it does not list: it fails closed), **SQL-affecting** (other backend code, goldens
  or corpus entries without a verification stamp) or **docs/tests only** (the paths it
  lists as such; a new file or directory is added to its lists in the same PR).
  The CI job `classify` runs it on every push and keeps one comment on the PR up to date.
- **Labels:** `needs-full-tier` for "needs full tier"; `run-ibmi` for SQL-affecting PRs
  and for changes that run on IBM i (new or changed own IBM i tests, the test models, the
  IBM i settings, the IBM i run tooling, the nox sessions, the supported Django test
  modules). CI only **adds** them; anyone may
  add `run-ibmi` by hand to request a run. The main session queues the run behind any
  other PUB400 job, posts the result on the PR (the SHA it ran on, the counts) and only
  then removes the label; the run must be on the PR's **latest** commit. The maintainer
  does not merge a PR that carries either label. Nothing in CI reacts to the labels.
- **The IBM i gate (`ibmi-gate`)**: a commit status on the PR's head, set by
  `.github/workflows/ibmi-gate.yml` (`scripts/ibmi_gate.py`, always main's copy:
  `pull_request_target` and `issue_comment`; the PR is only data, its code never runs).
  Red while the classification needs an IBM i run and no posted result covers the
  current content, by the same exceptions as below. Every run result comment
  starts with the marker `<!-- ibmi-run sha=<full sha> tier=targeted|full -->`
  (`full` for the full tier); only markers by the machine account or the
  maintainer count, and the maintainer may waive a commit with
  `<!-- ibmi-run sha=<full sha> waived -->`. Changes to the gate's two files are
  "needs full tier", and the PR comment names them for the maintainer's review.
  Not a required check at first; the maintainer then requires `ibmi-gate`.
- **A later push puts the labels back** (CI adds them again), with three exceptions that
  need no new run:
  - a push that only contains the verification stamps written by the run
    (`--record-verification`) on the previous commit, and files generated solely from
    them (e.g. the golden count in `docs/TEST_STATUS.md` via `nox -s test_status`). The
    PR comment then states the SHA the run was on and that the latest commit only adds
    those stamps and generated files;
  - a push (no rewrite) whose own files the classification marks as docs/tests only
    without an IBM i run, goldens and corpus entries excluded (e.g. renaming the
    changelog fragment to the PR number);
  - a conflict-free rebase whose own changes are identical (`git range-diff`) onto new
    `main` commits that the classification marks as docs/tests only, or that change
    only the IBM i gate's files (strictest class in their own PR, for the maintainer's
    review; they run nowhere on IBM i).
- Before review, and whenever a PR branch is behind `main`, Claude rebases it
  onto `main` and pushes it itself (`git push --force-with-lease`, PR branches
  only), so every PR is up to date and its commits stay signed (whether the
  rebase needs a new IBM i run: see the labels above). The maintainer
  never uses GitHub's "Update branch" button: with "approval of the most recent
  push" that would make the maintainer the last pusher, so nobody could approve
  the PR anymore.
- Claude opens pull requests and answers review comments, but never merges; the
  maintainer reviews and merges.

## 8. Directory structure

```
django-db2-for-i/
├── CLAUDE.md
├── README.md
├── CHANGELOG.md
├── LICENSE                      # BSD-3-Clause
├── CONTRIBUTING.md
├── pyproject.toml
├── noxfile.py
├── compose.yaml
├── .env.example
├── .gitignore
├── .devcontainer/
│   └── devcontainer.json
├── docker/
│   ├── Dockerfile               # targets: offline (no ODBC), full (with ODBC)
│   └── odbcinst.ini
├── docs/
│   ├── TEST_STATUS.md           # generated by scripts/update_test_status.py
│   ├── DJANGO_VERSIONS.md       # backend API impact per Django version
│   ├── IBMI_NOTES.md            # IBM i quirks and probe findings
│   └── DECISIONS.md             # lightweight decision records
├── django_db2_for_i/            # ENGINE = "django_db2_for_i"
│   ├── __init__.py
│   ├── base.py
│   ├── features.py
│   ├── operations.py
│   ├── schema.py
│   ├── introspection.py
│   ├── creation.py
│   ├── client.py
│   ├── compiler.py
│   ├── validation.py
│   ├── compat.py                # Django-version axis
│   ├── capabilities.py          # IBM i server axis
│   └── drivers/                 # driver axis
│       ├── __init__.py
│       ├── base.py
│       └── pyodbc.py
├── tests/
│   ├── conftest.py
│   ├── testapp/                 # models used by offline and pub400 tests
│   ├── offline/
│   │   ├── golden/
│   │   ├── test_queries.py
│   │   ├── test_schema.py
│   │   └── test_operations.py
│   ├── pub400/
│   └── django_settings/
│       ├── settings_full.py
│       └── settings_pub400.py
├── probes/                      # small scripts to verify IBM i behaviour
├── scripts/
│   ├── runtests.sh
│   └── update_test_status.py
├── vendor/                      # Django checkouts (gitignored)
└── test-results/                # logs (gitignored)
```

## 9. Phases

0. **Skeleton & environment.** Repo structure, `pyproject.toml`, `LICENSE`, `CONTRIBUTING.md`,
   Dockerfile (both targets), compose, devcontainer, nox sessions, `.env.example`, empty docs.
   Done when: `nox -s offline` runs (even with zero tests) and probe scripts against PUB400
   (a) connect and run `SELECT 1 FROM SYSIBM.SYSDUMMY1`, (b) report OS release, TR level,
   Db2 PTF Group level and system CCSID, and (c) report whether both libraries are journaled.
   Findings go into `docs/IBMI_NOTES.md`.
1. **Minimal backend.** Connection, cursor wrapper, driver layer, capabilities (detection +
   profiles), basic type mapping, `CREATE`/`DROP TABLE`, transactions, test DB creation
   including the "use existing schema" mode.
   Done when: Django modules `basic` and `transactions` run on 6.1 against PUB400, the offline
   tier has first golden files, and `TEST_STATUS.md` is generated.
2. **Queries & pagination.** `queries`, `lookup`, `ordering`, `aggregation`, `expressions`.
3. **Django 6.0 and 5.2 support.** Worked backwards in two steps: 6.1 → 6.0 first, then
   6.0 → 5.2. Build `compat.py` from real differences, extend nox matrix,
   fill `DJANGO_VERSIONS.md`.
4. **Schema editor completeness.** `schema`, `migrations`, `introspection`, `inspectdb`, and what
   they need: foreign keys, check constraints, introspection of every constraint, index ordering
   and text-field indexes.
   Also: verify the column order of created tables (issue #23).
5. **Returning & bulk.** `FINAL TABLE` returning columns, `bulk_create`, unique constraint variants,
   partial / expression / covering indexes; the `constraints`, `indexes` and `model_indexes` modules.
6. **Advanced.** Window functions, `JSONField`, db functions, DB-level `on_delete` (6.1+).
7. **PUB400 tier & release prep.** Curated smoke set, golden verification job, README, packaging.

Later: Django 6.2 LTS, additional drivers (Mapepire, `ibm_db`).
