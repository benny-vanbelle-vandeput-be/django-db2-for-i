# django-db2-for-i

<!-- badges:start -->
[![Django](https://img.shields.io/badge/Django-6.1%20%7C%206.0,%205.2%20planned-0C4B33)](https://www.djangoproject.com/)
![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-3776AB)
![IBM i](https://img.shields.io/badge/IBM%20i-7.5-054ADA)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)
[![offline CI](https://img.shields.io/github/actions/workflow/status/benny-vanbelle-vandeput-be/django-db2-for-i/offline.yml?branch=main&label=offline%20CI)](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/actions/workflows/offline.yml)
[![release](https://img.shields.io/github/v/release/benny-vanbelle-vandeput-be/django-db2-for-i?include_prereleases&label=release)](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)

[![Django modules](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/modules.json)](docs/TEST_STATUS.md)
[![passed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/passed.json)](docs/TEST_STATUS.md)
[![failed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/failed.json)](docs/TEST_STATUS.md)
[![skipped](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/skipped.json)](docs/TEST_STATUS.md)
[![expected failures](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/xfail.json)](docs/TEST_STATUS.md)
<!-- badges:end -->

A Django database backend for **Db2 for IBM i** (AS/400, iSeries).

> [!WARNING]
> **Alpha.** Minimal backend (phase 1) plus the first query work of phase 2:
> connections, transactions and savepoints, basic types, `CREATE`/`DROP
> TABLE`, test databases in an existing library, and the queries covered by
> the Django test modules in the status table below. Migrations that alter
> tables and many field types are not done yet. Not for production use. APIs
> and settings may change between alpha releases. See
> [Known limitations](docs/user/Known-Limitations.md).

## What the test badges mean

- **What the test badges count:** Django's own test modules (Django's
  `runtests.py`, the modules listed in [TEST_STATUS](docs/TEST_STATUS.md)),
  run against Db2 for i 7.5 on the shared PUB400 system, for one Python ×
  Django combination per row of badges. The label names it, for example
  `Django 6.1 · Python 3.14 on PUB400`; the Python part is left out while not
  every counted log records the same Python version. The counts come from the
  last recorded run of each module, not from every commit.
- **Not in these badges:** the full version matrix (every supported Python ×
  Django combination) runs only on a dedicated IBM i, not on the shared
  system. The backend's own pub400 tier (`tests/pub400/`) is separate and not
  counted.
- **offline CI:** the backend's offline tier on every commit, for every
  Python × Django combination, with no IBM i.
- **Django modules** `<run>/<total>`: how many of the Django version's test
  modules have a recorded run (a module run as several labels counts once),
  out of all test modules in that version's test suite (as `runtests.py`
  finds them, without the GIS tests).
- **passed:** the test ran and succeeded.
- **failed** = failures + errors + unexpected successes: the test ran and did
  not succeed (or an expected failure passed), and there is no known reason
  yet. This should be 0 on `main`.
- **skipped:** the test did not run, because it needs a feature the backend
  reports as unsupported (a feature flag that is off, for example something
  planned for a later phase) or because it is written for another database.
  Skips shrink as features are implemented.
- **expected failures:** the test runs but is known to fail because of a real
  Db2 for i limitation, each with a documented reason (see
  [Known limitations](docs/user/Known-Limitations.md)). If one starts
  passing, it is reported as an unexpected success (counted as failed).

Details per module: [docs/TEST_STATUS.md](docs/TEST_STATUS.md).

<!-- status:start -->
## Project status

### Releases

- **`v0.1.0a3`** (2026-10-20): Phase 2: queries & pagination (release run: 7 Django modules, 1249 tests, 0 failed).
- **`v0.1.0a2`** (2026-10-18): Encoding fixes (UTF-8 statement text, long strings intact) and the signed-tag release workflow.
- **`v0.1.0a1`** (2026-10-17): Phase 1: minimal backend (its code reports version 0.0.1.dev0).

### Phases

| Phase | Content | Status |
|---|---|---|
| 0 | Skeleton & environment | done |
| 1 | Minimal backend | done |
| 2 | Queries & pagination (ordering, lookup, aggregation, expressions, queries) | done |
| 3 | Django 6.0 and 5.2 support (plan approved: docs/phases/phase-3.md) | planned |
| 4 | Schema editor completeness | planned |
| 5 | Returning & bulk | planned |
| 6 | Advanced (window functions, JSONField, db functions, DB-level on_delete) | planned |
| 7 | PUB400 tier & release prep | planned |
| Encoding track | CCSID / UTF-8 investigation, findings A/B/C (released in 0.1.0a2) | done |

### Phase 3: supported modules per Django version

Tests and results from the last recorded run, see [TEST_STATUS](docs/TEST_STATUS.md).

| Module | Django 6.1 | Django 6.0 | Django 5.2 | Status |
|---|---|---|---|---|
| basic | 83 tests, OK (3 skipped) | planned | planned | planned |
| transactions | 88 tests, OK (3 skipped) | planned | planned | planned |
| ordering | 43 tests, OK | planned | planned | planned |
| lookup | 148 tests, OK (5 skipped, 2 expected failures) | planned | planned | planned |
| aggregation | 168 tests, OK (16 skipped) | planned | planned | planned |
| expressions | 213 tests, OK (5 skipped, 2 expected failures) | planned | planned | planned |
| queries | 506 tests, OK (21 skipped, 3 expected failures) | planned | planned | planned (split into labels Q1–Q5 because of its size) |

### Open tracks and notes

- Numeric filter values out of range give a driver error instead of no match ([#69](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/69)), next after 0.1.0a3.
- Offline query corpus from the PUB400 runs (approved: docs/proposals/offline-query-corpus.md), for Django 6.1 before phase 3 step A.
- Errors in `annotations` / `expressions_case`, outside the phase 2 modules ([#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82)).
- Verify the column order of created tables (phase 4, [#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23)).
- `DROP COLUMN` on a table with rows is cancelled by CPA32B2 (`HY008`), which raises the question of table rebuilds in phase 4 (see [IBMI_NOTES](docs/IBMI_NOTES.md)).
- Development runs on the shared PUB400 system; a dedicated IBM i is needed for the full test tier.
<!-- status:end -->

## Install

Alpha releases are published as [GitHub releases](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)
(sdist and wheel), not on PyPI:

```sh
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git@v0.1.0a3"
```

You also need unixODBC and the IBM i Access ODBC Driver, see
[ODBC driver setup](docs/user/ODBC-Driver-Setup.md).

## Usage

```python
DATABASES = {
    "default": {
        "ENGINE": "django_db2_for_i",
        "NAME": "MYLIB",  # library (schema); becomes CURRENT SCHEMA
        "HOST": "ibmi.example.com",
        "USER": os.environ["DB2I_USER"],
        "PASSWORD": os.environ["DB2I_PASSWORD"],
    }
}
```

All settings: [Configuration](docs/user/Configuration.md).

## Supported versions

| Component | Versions |
|---|---|
| Django | 6.1 (6.0 and 5.2 LTS are planned in phase 3; see [DJANGO_VERSIONS](docs/DJANGO_VERSIONS.md)) |
| Python | 3.12, 3.13, 3.14 (subject to each Django version's own support) |
| IBM i | 7.5 and later |

## Documentation

User documentation: [`docs/user/`](docs/user/Home.md), also published as the
[wiki](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/wiki)
(a generated mirror; edit `docs/user/`, never the wiki).

Project history and plans: one record per phase in [`docs/phases/`](docs/phases/README.md)
(goal, what was done, decisions, IBM i findings, test status); developer notes in
[`docs/DECISIONS.md`](docs/DECISIONS.md) and [`docs/IBMI_NOTES.md`](docs/IBMI_NOTES.md).

## Known limitations

- **`TimeField` has no fractional seconds.** Db2 for i `TIME` stores whole
  seconds only; the backend truncates microseconds before saving and in
  lookups, so `filter(t=value)` matches what was stored. Use a
  `DateTimeField` if you need sub-second precision.
- **Identifiers are uppercased.** Table and column names are created in
  uppercase; mixed-case `db_table` / `db_column` names are not preserved.
- **Every table Django writes to must be journaled.** Libraries created with
  `CREATE SCHEMA` are; libraries created with `CRTLIB` need a `QSQJRN`
  journal (see `docs/IBMI_NOTES.md`).

## IBM i Access ODBC Driver

The backend connects through pyodbc and the IBM i Access ODBC Driver. The driver
is IBM software under IBM's license terms. It is **not** part of this project and
is never redistributed. The development container installs it from IBM's
repository at build time. Container images that contain the driver must be
built locally or in private CI, and **never pushed to a public registry**.

## Development

All development and test runs happen in a container. The host only needs
Docker (e.g. Docker Desktop) with the `docker compose` plugin.

```sh
cp .env.example .env          # then fill in DB2I_* (never commit .env)
docker compose build          # builds the "offline" and "full" images
docker compose run --rm tests nox --list
docker compose run --rm tests nox -s offline
```

| Service | Build target | Contents | Use |
|---|---|---|---|
| `tests` | `full` | uv, Python 3.12–3.14, nox, unixODBC, IBM i Access ODBC Driver | all tiers, probes |
| `offline` | `offline` | same, without the IBM driver | offline tier, lint, CI |

- **Apple Silicon:** IBM publishes the Linux ODBC driver for amd64, i386 and
  ppc64el, not arm64. The `tests` service sets `platform: linux/amd64`, so it
  runs under emulation on arm64 hosts.
- **Licensing:** the `full` image contains the IBM i Access ODBC Driver.
  Build it locally or in private CI only, and **never push it to a public
  registry**. The `offline` image contains no IBM software.
- The devcontainer (`.devcontainer/`) attaches to the `tests` service.

## License

[BSD 3-Clause](LICENSE), the same license as Django. See
[CONTRIBUTING.md](CONTRIBUTING.md) for contribution terms.
