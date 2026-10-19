# Phase 0: Skeleton & environment

> Status: Done (2026-10-17)

Phase 0 ran before the pull request workflow existed: its commits went
straight to `main` and are linked below by commit. The phase ended with the
wrap-up commit [`3201061`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/3201061)
("docs: phase 0 wrap-up").

## Goal
Repo structure, `pyproject.toml`, `LICENSE`, `CONTRIBUTING.md`, Dockerfile
(both targets), compose, devcontainer, nox sessions, `.env.example`, empty docs.

Done when: `nox -s offline` runs (even with zero tests) and probe scripts
against PUB400 (a) connect and run `SELECT 1 FROM SYSIBM.SYSDUMMY1`, (b) report
OS release, TR level, Db2 PTF Group level and system CCSID, and (c) report
whether both libraries are journaled.

## What was done

### Project files
- Project brief (`CLAUDE.md`), BSD-3-Clause license, contributing guide,
  README, changelog, `.gitignore` ([`6218486`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/6218486),
  [`73ca552`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/73ca552)).
- `pyproject.toml` (Django 6.1, pyodbc required, hatchling) and every backend
  module as a docstring-only stub ([`76a6eee`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/76a6eee)).
- Claude Code project settings deny access to `.env`
  ([`e40b00b`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/e40b00b)).

### Container environment
- `docker/Dockerfile` with the `offline` and `full` targets (IBM i Access ODBC
  Driver pinned by version and SHA256), `compose.yaml`, devcontainer,
  `.env.example` ([`62a6a9a`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/62a6a9a)).
- compose never pulls or force-rebuilds its images
  ([`c7c9e01`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/c7c9e01)).

### Tests and CI
- noxfile with the sessions `lint`, `offline` (Python 3.12–3.14 × Django 6.1),
  `pub400` and `probe`; pytest tier markers; a conftest guard that fails when
  the offline tier tries to connect; offline smoke tests
  ([`48a923e`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/48a923e)).
- GitHub Actions workflow that runs the offline tier in the `offline` image
  ([`7d50456`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/7d50456)).

### Probes and docs
- Read-only PUB400 probes `reachability`, `connect`, `sysinfo`, `libraries`
  ([`fcba27b`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/fcba27b));
  the password length is scrubbed from driver messages
  ([`d8543a8`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/d8543a8));
  job CCSID query corrected, caller IP no longer printed
  ([`95c5970`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/95c5970)).
- Skeletons for `DECISIONS.md`, `DJANGO_VERSIONS.md`, `IBMI_NOTES.md`
  ([`cbb0b16`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/cbb0b16));
  PUB400 probe findings recorded ([`b520309`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/b520309)).

## Key decisions
- `debian:trixie-slim` with Python 3.12/3.13/3.14 installed by `uv`, `nox` as a
  uv tool ([DECISIONS](../DECISIONS.md#2026-10-16-container-base-image-and-python-provisioning)).
- The ODBC driver is installed from a pinned, SHA256-checked `.deb`, because
  IBM's apt repository is unsigned ([DECISIONS](../DECISIONS.md#2026-10-16-install-the-ibm-i-access-odbc-driver-from-a-pinned-checksummed-deb)).
- Own `odbcinst.ini` with a 64-bit-only driver entry
  ([DECISIONS](../DECISIONS.md#2026-10-16-own-odbcinstini-with-a-64-bit-only-entry)).
- pyodbc is a required dependency, not an extra
  ([DECISIONS](../DECISIONS.md#2026-10-16-pyodbc-is-a-required-dependency)).
- TLS (port 9471) by default, plain connections only with `DB2I_SSL=0`, no
  automatic fallback ([DECISIONS](../DECISIONS.md#2026-10-16-tls-by-default-no-automatic-fallback)).
- Connection settings as `DB2I_*` variables in `.env`, which Claude Code is
  denied access to ([DECISIONS](../DECISIONS.md#2026-10-16-secrets-handling)).
- compose services have no image name, so nothing is pulled or pushed by name
  ([DECISIONS](../DECISIONS.md#2026-10-16-compose-services-have-no-image-name)).
- Probes use pyodbc directly, not the driver layer
  ([DECISIONS](../DECISIONS.md#2026-10-16-probes-use-pyodbc-directly)).
- The full module layout exists as stubs from phase 0
  ([DECISIONS](../DECISIONS.md#2026-10-16-full-module-layout-as-stubs-in-phase-0)).
- hatchling as build backend; CI runs `nox -s lint offline` in the `offline`
  image ([DECISIONS](../DECISIONS.md#2026-10-16-build-backend-and-ci)).

## IBM i findings
- The IBM i Access ODBC Driver for Linux has no arm64 build; Apple Silicon
  runs the `full` image as `linux/amd64` ([IBMI_NOTES](../IBMI_NOTES.md#ibm-i-access-odbc-driver-for-linux)).
- PUB400's TLS certificate is trusted by the container's Debian CA store
  ([IBMI_NOTES](../IBMI_NOTES.md#reachability-and-tls-probe----reachability)).
- (a) `SELECT 1 FROM SYSIBM.SYSDUMMY1` works over TLS; `SQL_DBMS_VER` is
  `07.05.0015`; without `DBQ`, `CURRENT SCHEMA` is not one of the user's
  libraries; a wrong-password message contains the password length
  ([IBMI_NOTES](../IBMI_NOTES.md#connection-probe----connect)).
- (b) IBM i 7.5; TR level and Db2 PTF Group level are not readable for a
  normal PUB400 user (SQL0443), so TR-dependent capabilities need feature
  probes or `OPTIONS`; `QCCSID` and the server job CCSID are 273
  ([IBMI_NOTES](../IBMI_NOTES.md#os-release-tr-level-db2-ptf-group-level-ccsid-probe----sysinfo)).
- (c) None of the user's three libraries is journaled (no `QSQJRN`), so
  commitment control will not work until a journal exists
  ([IBMI_NOTES](../IBMI_NOTES.md#libraries-and-journaling-probe----libraries)).
  The journal was created at the start of phase 1, after approval.

## Test status at the end of the phase
- Offline tier: 16 passed, 0 failed, 0 skipped on each of Python 3.12, 3.13
  and 3.14 with Django 6.1 (`nox -s lint offline`, 2026-10-17). Smoke tests
  only (package imports, connection guard); no golden files yet.
- No pub400 tier tests and no Django test modules yet.
- `docs/TEST_STATUS.md` was maintained by hand until the generator of phase 1;
  the current, generated version is [TEST_STATUS.md](../TEST_STATUS.md).

## Carried forward
- Journal setup for the test libraries (proposal needing approval); done in
  phase 1.
- Redacting the password length in the backend's error mapping (phase 1).
- Driver interface, capabilities and `DatabaseWrapper` (phase 1).

## Links
- No release; phase 0 is part of the [0.1.0a1](../../CHANGELOG.md#010a1---2026-10-17)
  changelog section ("Phase 0: project skeleton"), tagged `v0.1.0a1`.
- [DECISIONS.md](../DECISIONS.md), [IBMI_NOTES.md](../IBMI_NOTES.md),
  [DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md).
