# django-db2-for-i

A Django database backend for **Db2 for IBM i** (AS/400, iSeries).

<!-- badges:start -->
[![release](https://img.shields.io/github/v/release/benny-vanbelle-vandeput-be/django-db2-for-i?include_prereleases&label=release)](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)
[![license](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/benny-vanbelle-vandeput-be/django-db2-for-i/offline.yml?branch=main&label=CI)](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/actions/workflows/offline.yml)

[![IBM i 7.5 ✅](https://img.shields.io/badge/IBM%20i-7.5%20%E2%9C%85-brightgreen)](docs/user/IBM-i-Requirements.md)

![Python 3.12 ✅](https://img.shields.io/badge/Python-3.12%20%E2%9C%85-brightgreen)
![Python 3.13 ✅](https://img.shields.io/badge/Python-3.13%20%E2%9C%85-brightgreen)
![Python 3.14 ✅](https://img.shields.io/badge/Python-3.14%20%E2%9C%85-brightgreen)

[![Django 5.2 ✅](https://img.shields.io/badge/Django-5.2%20%E2%9C%85-brightgreen)](docs/DJANGO_VERSIONS.md)
[![Django 6.0 ✅](https://img.shields.io/badge/Django-6.0%20%E2%9C%85-brightgreen)](docs/DJANGO_VERSIONS.md)
[![Django 6.1 ✅](https://img.shields.io/badge/Django-6.1%20%E2%9C%85-brightgreen)](docs/DJANGO_VERSIONS.md)
[![Django 6.2 🗓️](https://img.shields.io/badge/Django-6.2%20%F0%9F%97%93%EF%B8%8F-blue)](docs/DJANGO_VERSIONS.md)

<sub>✅ supported · 🚧 in development · 🗓️ planned · ⚠️ end of life, no longer maintained · ❌ not supported</sub>
<!-- badges:end -->

<!-- tests:start -->
## Test status

### Django 6.1 ✅

[![passed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.1/passed.json)](docs/TEST_STATUS.md)
[![skipped](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.1/skipped.json)](docs/TEST_STATUS.md)
[![expected failures](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.1/xfail.json)](docs/TEST_STATUS.md)
[![failed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.1/failed.json)](docs/TEST_STATUS.md)

| Test set | Passed | Skipped | Expected failures | Failed | Last run |
|---|---|---|---|---|---|
| Offline tests | 2958 | 2 | 0 | 0 | 2026-10-29 21:02:46 UTC |
| IBM i tests | 328 | 0 | 1 | 0 | 2026-10-29 12:56:12 UTC |
| Django suite on IBM i | 2117 | 189 | 53 | 0 | 2026-10-29 12:04:46 UTC |
| Replay tests | 2544 | 0 | 0 | 0 | 2026-10-29 21:02:56 UTC |

### Django 6.0 ✅

[![passed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.0/passed.json)](docs/TEST_STATUS.md)
[![skipped](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.0/skipped.json)](docs/TEST_STATUS.md)
[![expected failures](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.0/xfail.json)](docs/TEST_STATUS.md)
[![failed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/6.0/failed.json)](docs/TEST_STATUS.md)

| Test set | Passed | Skipped | Expected failures | Failed | Last run |
|---|---|---|---|---|---|
| Offline tests | 2959 | 1 | 0 | 0 | 2026-10-29 21:00:45 UTC |
| IBM i tests | 328 | 0 | 1 | 0 | 2026-10-29 10:35:19 UTC |
| Django suite on IBM i | 2021 | 169 | 54 | 0 | 2026-10-29 09:48:04 UTC |
| Replay tests | 2484 | 0 | 0 | 0 | 2026-10-29 21:00:58 UTC |

### Django 5.2 ✅

[![passed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/5.2/passed.json)](docs/TEST_STATUS.md)
[![skipped](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/5.2/skipped.json)](docs/TEST_STATUS.md)
[![expected failures](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/5.2/xfail.json)](docs/TEST_STATUS.md)
[![failed](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/benny-vanbelle-vandeput-be/django-db2-for-i/main/docs/badges/5.2/failed.json)](docs/TEST_STATUS.md)

| Test set | Passed | Skipped | Expected failures | Failed | Last run |
|---|---|---|---|---|---|
| Offline tests | 2957 | 1 | 0 | 0 | 2026-10-29 20:58:19 UTC |
| IBM i tests | 323 | 3 | 1 | 0 | 2026-10-29 08:22:24 UTC |
| Django suite on IBM i | 1982 | 163 | 55 | 0 | 2026-10-29 07:35:19 UTC |
| Replay tests | 2440 | 0 | 0 | 0 | 2026-10-29 20:58:33 UTC |

### About the tests

- **Offline tests:** unit tests and SQL checks written for this project (golden
  files of the generated SQL and DDL, operations, the driver layer). They run in
  GitHub CI on every commit, for every Python × Django combination, without an IBM i.
- **IBM i tests:** tests written for this project, run against a real Db2 for i
  (PUB400, IBM i 7.5): queries with model instances, schema changes, transactions,
  and every golden file executed on the server. They run for every backend change.
- **Django suite on IBM i:** Django's official test suite, limited to the modules that use
  the database and that this backend supports so far: `aggregation`, `basic`, `expressions`, `inspectdb`, `introspection`, `lookup`, `migrate_signals`, `migrations`, `ordering`, `queries`, `schema`, `transactions`. They run on
  PUB400 before every release (the status run) and for the modules a change
  touches.
- **Replay tests:** the SQL of every passing test of that Django test suite is
  recorded on IBM i; GitHub CI generates it again on every commit, without an IBM i,
  and compares (counted per recorded statement). See
  [docs/REPLAY_TESTS.md](docs/REPLAY_TESTS.md).

**failed** = failures + errors + unexpected successes; it should be 0 on `main`.
**Skipped** tests need a feature that is off (see the feature flags) or another
database; **expected failures** are known Db2 for i limitations, each with a reason
([Known limitations](docs/user/Known-Limitations.md)).

Feature flags: [docs/FEATURES.md](docs/FEATURES.md) (34 enabled on Django 6.1) · All details: [docs/TEST_STATUS.md](docs/TEST_STATUS.md)
<!-- tests:end -->

<!-- status:start -->
## Project status

**Phase 5: Returning & bulk** (in progress)

| Step | State | Pull requests |
|---|---|---|
| 0: QTEMP probes and the baseline of the four modules | in progress |  |
| Names: truncates_names, supports_sequence_reset | planned |  |
| A: returning and bulk insert (bulk_create) | planned |  |
| C: partial and expression indexes (indexes, model_indexes) | planned |  |
| D: unique variants (constraints) | planned |  |
| E: chunked reads, self-referencing UPDATE / DELETE | planned |  |
| B: conflicts through MERGE, or the exit | planned |  |
| Close-out: supported modules, status run, phase record | planned |  |

| Phase | Content | Status |
|---|---|---|
| [0](docs/phases/phase-0.md) | Skeleton & environment | done |
| [1](docs/phases/phase-1.md) | Minimal backend | done |
| [2](docs/phases/phase-2.md) | Queries & pagination (ordering, lookup, aggregation, expressions, queries) | done |
| [3](docs/phases/phase-3.md) | Django 6.0 and 5.2 support | done |
| [4](docs/phases/phase-4.md) | Schema editor completeness | done |
| [5](docs/phases/phase-5.md) | Returning & bulk | in progress |
| 6 | Advanced (window functions, JSONField, db functions, DB-level on_delete) | planned |
| 7 | PUB400 tier & release prep | planned |

Latest release: **`v0.1.0b1`** (2026-10-29): First beta: the pre-beta review (#190, #191) done; status runs on 5.2, 6.0 and 6.1, 22 runs each, 0 failed. ([CHANGELOG](CHANGELOG.md))

Open tracks:

- Errors in `annotations` / `expressions_case`, outside the phase 2 modules ([#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82)).
- Development runs on the shared PUB400 system; a dedicated IBM i is needed for the full test tier.
<!-- status:end -->

> [!WARNING]
> **Beta.** Connections, transactions and savepoints, the basic field types,
> test databases in an existing library, the queries covered by the Django
> test modules above (filters, lookups, ordering, pagination, aggregation,
> expressions, compound queries) and the schema editor (migrations that
> create and alter tables, foreign keys, check constraints, indexes,
> introspection and `inspectdb`) work on Django 5.2, 6.0 and 6.1, within the
> [known limitations](docs/user/Known-Limitations.md). `bulk_create()` with
> returned keys, unique constraint variants, partial and expression indexes
> (phase 5), window functions, `JSONField` and database functions (phase 6)
> are not done yet. Not for production use; APIs and settings may change
> between beta releases.

## What it is

`django_db2_for_i` lets a Django project use Db2 for i, the database built
into IBM i, as `ENGINE = "django_db2_for_i"`. It is written from scratch,
driven by Django's own test suite: every optional feature starts off and is
enabled only when the related Django tests pass against a real IBM i (see the
[feature flags](docs/FEATURES.md)). It talks to the server through pyodbc and
the IBM i Access ODBC Driver.

## Requirements

- **IBM i 7.5** or later, reachable on the database host server port (8471,
  or 9471 with TLS); the tables Django writes to must be journaled. See
  [IBM i requirements](docs/user/IBM-i-Requirements.md).
- **IBM i Access ODBC Driver** and unixODBC, see
  [ODBC driver setup](docs/user/ODBC-Driver-Setup.md).
- **Python** 3.12, 3.13 or 3.14.
- **Django** 5.2 LTS (5.2.12 or later), 6.0 (6.0.3 or later) or 6.1; always
  use the latest security release of your Django version
  ([supported versions](docs/DJANGO_VERSIONS.md)).

## Installation

Releases are published as
[GitHub releases](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases)
from signed tags, not on PyPI. Install one from its tag:

```sh
pip install "django-db2-for-i @ git+https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i.git@v0.1.0b1"
```

Details: [Installation](docs/user/Installation.md).

## Configuration

```python
import os

DATABASES = {
    "default": {
        "ENGINE": "django_db2_for_i",
        "NAME": "MYLIB",  # library (schema) for unqualified table names
        "HOST": "ibmi.example.com",
        "USER": os.environ["DB2I_USER"],
        "PASSWORD": os.environ["DB2I_PASSWORD"],
        "OPTIONS": {
            "ssl": True,  # TLS on port 9471 (default); False uses port 8471
            "isolation_level": "*CS",  # commitment control level (default)
            "login_timeout": 10,  # seconds (default)
            # "inquiry_message_reply": "*SYSRPYL",  # allow DROP COLUMN, see the docs
        },
        "TEST": {"NAME": "MYTESTLIB", "CREATE_DB": False},  # an existing library
    }
}
```

All settings and options: [Configuration](docs/user/Configuration.md).

## Known limitations

The most visible ones: `TimeField` has no fractional seconds, table and
column names are uppercase, every table Django writes to must be journaled,
`DROP COLUMN` needs a system reply list entry, and `StringAgg` requires
Django 6.0 or later. The full list, with workarounds:
[Known limitations](docs/user/Known-Limitations.md); errors by SQLCODE:
[Troubleshooting](docs/user/Troubleshooting.md).

## Documentation

- User documentation: [`docs/user/`](docs/user/Home.md), also published as the
  [wiki](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/wiki)
  (a generated mirror; edit `docs/user/`, never the wiki).
- Project history and plans: one record per phase in
  [`docs/phases/`](docs/phases/README.md); [CHANGELOG](CHANGELOG.md).
- Developer notes: [decisions](docs/DECISIONS.md), [IBM i findings](docs/IBMI_NOTES.md),
  [Django versions](docs/DJANGO_VERSIONS.md), [test status](docs/TEST_STATUS.md),
  [feature flags](docs/FEATURES.md), [offline query corpus](docs/REPLAY_TESTS.md).

## Development

All development and test runs happen in a container; the host only needs
Docker (e.g. Docker Desktop) with the `docker compose` plugin. The workflow,
step by step with the exact commands, is in [docs/WORKFLOW.md](docs/WORKFLOW.md);
`bin/help` shows its quick start and topics in the terminal. First-time setup:
run `bin/setup` in your own terminal (it asks for the `.env` values; never
commit `.env`).

The scripts in `bin/` run on the host; each has `--help` and `--dry-run`:

| Script | What it does |
|---|---|
| `bin/help` | the workflow guide: the quick start and the topics (`bin/help <topic>`) |
| `bin/setup` | first-time setup: images, `.env` (asked in your own terminal), `vendor/` checkouts |
| `bin/doctor` | checks the environment, then one connection to PUB400 |
| `bin/check` | what CI does, locally: lint, offline tests, corpus replay, gate, classification |
| `bin/verify` | verifies changed SQL and new tests on IBM i and writes the stamps |
| `bin/ibmi-test` | chosen own IBM i tests, Django test labels, `--affected` or `--full-tier` on IBM i |
| `bin/probe` | IBM i probes by name: `qtemp_` probes (read-only or QTEMP); `lib_` probes only with `--approved <link>` to the maintainer's approval; `--publish` puts a result into the repository |
| `bin/status` | regenerates the status pages; shows the PUB400 lock and labelled pull requests |
| `bin/ibmi-cleanup` | lists (`--yes`: drops) the leftover test tables of a crashed run |
| `bin/status-run` | the status run on IBM i, per Django version, resumable |
| `bin/release-prepare` | checks the release preconditions and opens the release pull request |
| `bin/worktree-remove` | removes a merged worktree, keeping its test results in the main checkout |

| Test set | How it runs | Needs |
|---|---|---|
| Offline tests | `docker compose run --rm offline nox -s lint offline` | nothing |
| IBM i tests | `scripts/pub400.sh ibmi [<django>]` | an IBM i (`.env`) |
| Django suite on IBM i | `scripts/django_suite.sh <django> --clean <module>`; before a release `scripts/pub400.sh status_run <django>` | an IBM i, `vendor/django-<version>` |
| Replay tests | `docker compose run --rm offline nox -s "replay(3.14-django6.1)"` | nothing |

`nox -s test_status` regenerates this README's generated sections and
[docs/TEST_STATUS.md](docs/TEST_STATUS.md); `nox -s features` regenerates
[docs/FEATURES.md](docs/FEATURES.md).

**IBM i rules for contributors** (details in [CONTRIBUTING.md](CONTRIBUTING.md)):
never run the full Django test suite against a shared system such as PUB400,
use one connection at a time, keep probes read-only (only `QTEMP` may be
changed), and never put credentials in the repository; `.env` stays local.

| Service | Build target | Contents | Use |
|---|---|---|---|
| `tests` | `full` | uv, Python 3.12–3.14, nox, unixODBC, IBM i Access ODBC Driver | all test sets, probes |
| `offline` | `offline` | the same without the IBM driver | offline test sets, lint, CI |

On Apple Silicon the `tests` service runs as `linux/amd64` under emulation:
IBM publishes the Linux driver for amd64, i386 and ppc64el, not arm64. The
devcontainer (`.devcontainer/`) attaches to the `tests` service.

## Contributing

Contributions are welcome under the project's license; see
[CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, the test sets, golden
files and changelog fragments.

## License

[BSD 3-Clause](LICENSE), the same license as Django.

**The IBM i Access ODBC Driver** is IBM software under IBM's license terms. It
is not part of this project and is never redistributed. The development
container installs it from IBM's repository at build time; container images
that contain it are built locally or in private CI and **never published** to
a public registry.
