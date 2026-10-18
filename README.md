# django-db2-for-i

<!-- badges:start -->
[![Django](https://img.shields.io/badge/Django-6.1%20%7C%205.2%20planned-0C4B33)](https://www.djangoproject.com/)
![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.13%20%7C%203.14-3776AB)
![IBM i](https://img.shields.io/badge/IBM%20i-7.5-054ADA)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)
[![offline CI](https://img.shields.io/github/actions/workflow/status/benny-vanbelle-vandeput-be/django-db2-for-i/offline.yml?branch=main&label=offline%20CI)](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/actions/workflows/offline.yml)
[![release](https://img.shields.io/github/v/release/benny-vanbelle-vandeput-be/django-db2-for-i?include_prereleases&label=release)](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)
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

- **Django tests (PUB400):** Django's own test suite (the modules listed in
  [TEST_STATUS](docs/TEST_STATUS.md)) run against Db2 for i 7.5 on the shared
  PUB400 system. The counts come from the last recorded run of each module,
  not from every commit.
- **passed:** the test ran and succeeded.
- **failed:** the test ran and did not succeed, and there is no known reason
  yet. This should be 0 on `main`.
- **skipped:** the test did not run, because it needs a feature the backend
  reports as unsupported (a feature flag that is off, for example something
  planned for a later phase) or because it is written for another database.
  Skips shrink as features are implemented.
- **expected failures:** the test runs but is known to fail because of a real
  Db2 for i limitation, each with a documented reason (see
  [Known limitations](docs/user/Known-Limitations.md)). If one starts
  passing, it is reported as an unexpected success (counted as failed).
- **offline CI:** the backend's own offline tests, on every commit, with no
  IBM i.

Details per module: [docs/TEST_STATUS.md](docs/TEST_STATUS.md).

<!-- status:start -->
## Project status

### Releases

- **`v0.1.0a2`** (2026-10-18): Encoding fixes (UTF-8 statement text, long strings intact) and the signed-tag release workflow.
- **`v0.1.0a1`** (2026-10-17): Phase 1: minimal backend (its code reports version 0.0.1.dev0).

### Phases

| Phase | Content | Status |
|---|---|---|
| 0 | Skeleton & environment | done |
| 1 | Minimal backend | done |
| 2 | Queries & pagination (ordering, lookup, aggregation, expressions, queries) | in progress |
| 3 | Django 5.2 support | planned |
| 4 | Schema editor completeness | planned |
| 5 | Returning & bulk | planned |
| 6 | Advanced (window functions, JSONField, db functions, DB-level on_delete) | planned |
| 7 | PUB400 tier & release prep | planned |
| Encoding track | CCSID / UTF-8 investigation, findings A/B/C (released in 0.1.0a2) | done |

### Phase 2 modules

Tests and results from the last recorded run, see [TEST_STATUS](docs/TEST_STATUS.md).

| Module | Tests | Result | Status |
|---|---|---|---|
| ordering | 43 | OK | done |
| lookup | 148 | OK (5 skipped, 2 expected failures) | done |
| aggregation | 168 | OK (18 skipped) | done |
| expressions | 213 | FAILED (37 errors, 14 skipped) | in progress (first run recorded, fixes being merged) |
| queries |  | not run yet | planned (split into labels Q1–Q5 because of its size) |

### Open tracks and notes

- Verify the column order of created tables (phase 4, [#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23)).
- `DROP COLUMN` on a table with rows is cancelled by CPA32B2 (`HY008`), which raises the question of table rebuilds in phase 4 (see [IBMI_NOTES](docs/IBMI_NOTES.md)).
- Durations track: `DurationField` storage, `timedelta` values, exact timestamp subtraction (approved; follows the `expressions` fixes, and removes the duration skips).
- Development runs on the shared PUB400 system; a dedicated IBM i is needed for the full test tier.
<!-- status:end -->

## Install

Alpha releases are published as [GitHub releases](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)
(sdist and wheel), not on PyPI:

```sh
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git@v0.1.0a2"
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
| Django | 5.2 LTS, 6.1 (development currently targets 6.1 only) |
| Python | 3.12, 3.13, 3.14 (subject to each Django version's own support) |
| IBM i | 7.5 and later |

## Documentation

User documentation: [`docs/user/`](docs/user/Home.md), also published as the
[wiki](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/wiki)
(a generated mirror; edit `docs/user/`, never the wiki).

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
