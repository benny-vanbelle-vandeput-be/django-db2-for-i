# Decision records

Lightweight records of non-obvious decisions: date, decision, why, alternatives.

## 2026-10-16: Container base image and Python provisioning
- **Decision:** `debian:trixie-slim` with Python 3.12/3.13/3.14 installed by `uv`
  (pinned uv version), plus `nox` as a uv tool.
- **Why:** one image serves every Python version in the matrix; uv is also nox's
  venv backend, so interpreter and environment handling come from one tool.
- **Alternatives:** official `python:*` images (one Python per image, so a matrix
  of images); Ubuntu base (larger, no benefit for the driver).

## 2026-10-16: Install the IBM i Access ODBC Driver from a pinned, checksummed .deb
- **Decision:** download `ibm-iaccess-<version>.amd64.deb` from IBM's repository,
  verify its SHA256, and install it with apt. Version and checksum are build args.
- **Why:** IBM's apt repository is unsigned (no `Release.gpg`/`InRelease`; IBM's own
  `.list` file uses `[trusted=yes]`). A pinned checksum gives integrity and
  reproducible builds.
- **Alternatives:** IBM's `.list` with `[trusted=yes]` (no integrity check, version
  drifts silently).

## 2026-10-16: Own odbcinst.ini with a 64-bit-only entry
- **Decision:** `docker/odbcinst.ini` replaces the package's registration; the
  common name `IBM i Access ODBC Driver` points to `lib64/libcwbodbc.so`.
- **Why:** the package registers `Driver=` with a 32-bit `lib/` path that the amd64
  package does not ship, relying on unixODBC's `Driver64` handling. An explicit
  entry is unambiguous; the build fails if the library is missing or unresolved.
- **Alternatives:** keep the package registration; use the
  `IBM i Access ODBC Driver 64-bit` name in connection strings.

## 2026-10-16: pyodbc is a required dependency
- **Decision:** `pyodbc` is in `dependencies`, not an extra.
- **Why:** it is the only driver; with an extra, a plain
  `pip install django-db2-for-i` would not work.
- **Revisit:** when a second driver (Mapepire, `ibm_db`) is added, move each driver
  to its own extra.

## 2026-10-16: TLS by default, no automatic fallback
- **Decision:** `DB2I_SSL=1` (port 9471) is the default. Plain connections (8471)
  only with an explicit `DB2I_SSL=0`. Probes report certificate problems as such
  and never fall back automatically.
- **Why:** the password crosses the public internet when using PUB400.
- **Alternatives:** plain by default (credentials unencrypted); automatic fallback
  (silently downgrades security).

## 2026-10-16: Secrets handling
- **Decision:** all connection settings use the `DB2I_` prefix and live in `.env`
  (gitignored, excluded from the Docker build context). compose injects them into
  the `tests` container. `.claude/settings.json` denies Claude Code access to `.env`.
- **Why:** enforce "never read or print `.env`" instead of relying on convention.
- **Limitation:** Bash deny rules are prefix-based and not exhaustive; the
  Read/Edit/Write rules are exact.

## 2026-10-16: compose services have no image name
- **Decision:** `tests` and `offline` only have a `build:` section.
- **Why:** with an explicit `image:` name, compose would either rebuild on every run
  (`pull_policy: build`) or try to pull that name from Docker Hub, where anyone
  could publish it. The `full` image must also never be pushed.

## 2026-10-16: Probes use pyodbc directly
- **Decision:** `probes/` talk to pyodbc directly, not through `django_db2_for_i.drivers`.
- **Why:** the driver interface is designed in phase 1; probes must not depend on
  it, and they must keep working as an independent check of IBM i behaviour.

## 2026-10-16: Full module layout as stubs in phase 0
- **Decision:** every backend module exists from phase 0 as a docstring-only stub
  stating its responsibility and the phase that implements it.
- **Why:** makes the three-axis architecture visible from the start.

## 2026-10-16: Build backend and CI
- **Decision:** hatchling as build backend. CI (GitHub Actions) builds the `offline`
  image target and runs `nox -s lint offline` inside it.
- **Why:** hatchling supports SPDX `license` and `license-files` and is widely used.
  Running CI in the same image as local development keeps one environment.
- **Alternatives:** `uv_build`, setuptools; running nox directly on the runner.

## 2026-10-17: CharField maps to NVARCHAR (CCSID 1200)
- **Decision:** `CharField(max_length=n)` (and the other `max_length` string
  fields) map to `NVARCHAR(n)`, i.e. UTF-16 (CCSID 1200).
- **Why:** probes `session` and `probe_write` (docs/IBMI_NOTES.md) show that
  `NVARCHAR(n)` counts UTF-16 code units. That equals Django's `max_length`
  (code points) for every BMP character: `é` × 10 fits in `NVARCHAR(10)`,
  `é` × 11 is rejected. `VARCHAR(n) CCSID 1208` counts bytes, so `é` × 10
  does not fit in `VARCHAR(10)`. The job CCSID (273) cannot store emoji at all.
- **Known deviation:** a non-BMP character (emoji) takes 2 of the `n` units, so
  a value that passes Django's `max_length` validation can be rejected by the
  driver (`22001`, never truncated). Example: 6 emoji fit `max_length=10` in
  Django but not `NVARCHAR(10)`.
- **Row length impact:** Db2 for i limits a row to 32,766 bytes (LOB columns
  excepted). `NVARCHAR(n)` uses 2 bytes per unit plus a 2-byte length, so
  `CharField(max_length=255)` takes 512 bytes; about 63 such columns fill a
  row. With `VARCHAR CCSID 1208` sized in bytes the same column could take
  half (ASCII) but would not enforce `max_length`.
- **Alternatives:** `VARCHAR(n) CCSID 1208` (byte length, rejects non-ASCII
  values at `max_length`); `VARCHAR(4n) CCSID 1208` (no length enforcement,
  wastes row length); `VARCHAR(n)` in the job CCSID (no emoji, CCSID-dependent).
- **Revisit:** if the emoji deviation shows up in Django's test suite, consider
  `NVARCHAR(2n)` plus a `CHARACTER_LENGTH` check constraint.

## 2026-10-17: TrueAutoCommit=1 is the driver default
- **Decision:** the pyodbc driver connects with `TRUEAUTOCOMMIT=1`.
- **Why:** Django assumes a single statement in autocommit mode is atomic.
  Probe `probe_autocommit` (docs/IBMI_NOTES.md) shows that with the driver
  default `TRUEAUTOCOMMIT=0`, a multi-row `INSERT` that fails on its last row
  leaves the earlier rows behind; with `TRUEAUTOCOMMIT=1` it leaves none.
- **Consequence:** every data change, also in autocommit mode, runs under
  commitment control, so every table Django writes to must be journaled
  (libraries need a `QSQJRN` journal). `SQLCODE -7008` gets an explicit error
  message pointing at that.
- **Alternatives:** keep `TRUEAUTOCOMMIT=0` (works on unjournaled libraries,
  but breaks statement atomicity silently); `CMT=0` (*NONE; no transactions).

## 2026-10-17: Extended dynamic SQL packages off (XDYNAMIC=0)
- **Decision:** the pyodbc driver connects with `XDYNAMIC=0`; the probes do too.
  Enabling packages is possible through driver attributes in `OPTIONS`
  (`XDYNAMIC`, `DFTPKGLIB`, `PKG`), but nothing sets them.
- **Why:** the driver default is `XDYNAMIC=1` (IBM's connection string keyword
  documentation), which creates `*SQLPKG` objects on the server, in `QGPL` by
  default. The phase 1 probes created `QGPL/PYTHONANBI` that way
  (docs/IBMI_NOTES.md). That is a write on a shared system, uses storage, may
  need authority on the package library, and Django's many distinct
  statements plus the test suite's create/drop churn make packages useless
  or harmful.
- **Alternatives:** keep the default (packages in `QGPL`); packages in our own
  library via `DFTPKGLIB` (still churn).
- **Revisit:** in a tuning phase with benchmarks, together with block fetch,
  lazy close and `QAQQINI` options (all out of scope until then).

## 2026-10-17: Capability detection and profiles
- **Decision:** `capabilities.py` selects a profile by OS release (from
  `SQL_DBMS_VER`, e.g. `07.05.0015`), then runs targeted probes for
  capabilities that depend on TR / Db2 PTF Group level, caching the result per
  `(host, server version)`. `OPTIONS["capabilities"]` can name a profile (no
  connection needed, used offline) and/or override single capabilities;
  unknown names and wrong types are rejected.
- **Releases:** below 7.5 is refused. A newer release than any profile uses
  the newest profile, with its actual release recorded, and logs a warning on
  logger `django_db2_for_i` (once per server and process, because detection
  is cached). Capabilities rarely disappear; a new profile is added once that
  release is probed. (The first version, commit `c78ac26`, did not warn; the
  warning was added in `82ce20c` after review.)
- **Targeted probes:** none yet. Everything in the 7.5 profile was verified
  on PUB400 (probe `features`) and is part of 7.5 itself according to IBM's
  release history. PUB400's TR level cannot be read, so features added by a
  later 7.5 TR must get a targeted probe, not a profile value.
- **Alternatives:** read the TR / PTF group level (not authorized for normal
  users on PUB400); probe every capability on every connection (extra load
  on shared systems for no gain).

## 2026-10-17: Database settings mapping
- **Decision:** `NAME` is the default schema (library), uppercased and passed
  as `DBQ`; `HOST` is the system; `PORT` is refused (the driver uses the
  database host server port, 8471 or 9471 with TLS). Backend options live in
  `OPTIONS`: `ssl`, `isolation_level`, `login_timeout`, `driver`,
  `driver_attributes`, `capabilities`; unknown keys are refused.
- **Why:** an IBM i system has one relational database; what Django calls a
  database maps to a schema, which is also what test database creation
  creates or reuses. Refusing unknown options and `PORT` catches typos and
  settings that would otherwise be silently ignored.
- **Alternatives:** `NAME` = RDB name with the schema in `OPTIONS` (makes the
  test database a schema setting, against Django's model).

## 2026-10-17: Rows are plain tuples
- **Decision:** the pyodbc driver converts `pyodbc.Row` objects to tuples in
  `fetchone`/`fetchmany`/`fetchall`.
- **Why:** the driver interface promises tuples; Django and its test suite
  compare rows with tuples (`pyodbc.Row` is not equal to a tuple). Found by
  the pub400 smoke check.
- **Cost:** one tuple per row; revisit with benchmarks in a tuning phase.

## 2026-10-17: BOOLEAN is required for now
- **Decision:** `BooleanField` maps to `BOOLEAN`. A server or configuration
  without `has_boolean_type` is refused with `NotSupportedError` when the
  capabilities are resolved.
- **Why:** the minimum release 7.5 has BOOLEAN; the `SMALLINT` + `CHECK`
  fallback (needed only if 7.4 is ever added) is not implemented yet, and a
  silent wrong mapping would be worse than a clear error.

## 2026-10-17: sql_flush uses TRUNCATE, DELETE for referenced tables
- **Decision:** `sql_flush()` reads the foreign keys among the flushed tables
  and their identity columns from `QSYS2.SYSREFCST` / `SYSCST` / `SYSCOLUMNS`.
  Unreferenced tables: `TRUNCATE TABLE t [RESTART IDENTITY]`. Tables
  referenced by a foreign key: `DELETE FROM t` (children first), and with
  `reset_sequences` `ALTER TABLE t ALTER COLUMN c RESTART WITH <IDENTITY_START>`.
- **Why:** Db2 for i refuses `TRUNCATE` on a referenced table even when the
  child is empty (probe `probe_operations`); `TRUNCATE` is faster otherwise
  and works inside a transaction.
- **Alternatives:** `DELETE` for every table (slower, no catalog query);
  dropping and re-adding constraints (DDL churn on a shared system).
- **Limits:** cycles between referenced tables are broken in name order and
  may fail; children outside the flushed set are not followed.

## 2026-10-17: last_insert_id via IDENTITY_VAL_LOCAL()
- **Decision:** `last_insert_id()` runs `SELECT IDENTITY_VAL_LOCAL() FROM
  SYSIBM.SYSDUMMY1` and converts the `DECIMAL` result to `int`.
- **Why:** returning columns are off until phase 5. Django only calls it after
  a single-row `INSERT ... VALUES`, the only case where the value is the new
  row's key (after a multi-row insert it is the last row's value).
