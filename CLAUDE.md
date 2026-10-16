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
- **Respect shared systems.** Never run the full Django suite against PUB400 or any shared system
  (see "Initial test system: PUB400" for what is allowed).
- Record non-obvious design decisions in `docs/DECISIONS.md` (date, decision, why, alternatives).
- At the end of each phase: update `docs/TEST_STATUS.md`, `CHANGELOG.md`, commit,
  and summarize what was done and what comes next.
- All code, comments and docs in English.

## 3. Supported versions

### Django
- Supported now: **Django 5.2 LTS and 6.1**. Not 6.0, not 4.2.
- Policy: follow Django's own support table. A version stays supported until it reaches
  end of life (end of security support), then it is dropped in the next release of this backend.
  When **6.2 LTS** ships it is added alongside 5.2 and 6.1.
- Develop phases 0–2 against **6.1 only**. Add 5.2 support after phase 2.
- For each supported version, read the **"Database backend API"** section of the Django
  release notes and record the impact in `docs/DJANGO_VERSIONS.md`.

### Python
- Python **3.12, 3.13, 3.14** — verify per Django version in its release notes
  (including the minimum 5.2.x patch release that supports 3.14).

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
- PUB400 limits connections per IP: one connection per run, `--parallel=1`, no retry storms.
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
  tests passing, offline tests, and an entry in `CHANGELOG.md`.

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

### Tier 1 — `offline` (no IBM i needed; every commit, in CI)
- Compile querysets with `query.get_compiler(using).as_sql()` and compare SQL + params
  to golden files in `tests/offline/golden/`.
- Collect DDL with `connection.schema_editor(collect_sql=True)` for model and migration operations.
- Unit-test pure `DatabaseOperations` methods.
- Run for every capability profile (initially only 7.5).
- Each golden file records whether it has been **verified** against a real IBM i
  (version + date). Unverified goldens are listed in a report.
- The `DatabaseWrapper` must never open a connection in this tier; a fixture fails loudly if it tries.

### Tier 2 — `pub400` (small curated smoke set for a shared, restricted system)
- Works in **pre-existing libraries**: `creation.py` supports a "use existing schema,
  never CREATE/DROP SCHEMA" mode and cleans up its own tables.
- Multi-database tests are skipped if no second library is configured.
- Includes a job that executes all golden-file SQL to verify it.
- Keep the load light. Check PUB400's terms of use and ODBC availability.

### Tier 3 — `full` (Django's `runtests.py` against a dedicated IBM i)
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
  Full matrix: at the end of each phase and before every release.

### Version matrix
- offline: every Python × every Django version.
- pub400: one combination (newest Python, newest Django).
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
3. **Django 5.2 support.** Build `compat.py` from real differences, extend nox matrix,
   fill `DJANGO_VERSIONS.md`.
4. **Schema editor completeness.** `schema`, `migrations`, `introspection`, `inspectdb`.
5. **Returning & bulk.** `FINAL TABLE` returning columns, `bulk_create`, constraints, indexes.
6. **Advanced.** Window functions, `JSONField`, db functions, DB-level `on_delete` (6.1+).
7. **PUB400 tier & release prep.** Curated smoke set, golden verification job, README, packaging.

Later: Django 6.2 LTS, additional drivers (Mapepire, `ibm_db`).
