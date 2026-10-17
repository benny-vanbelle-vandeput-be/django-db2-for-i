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
  release is probed. (The first version, commit `3071ed8`, did not warn; the
  warning was added in `8875f31` after review.)
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

## 2026-10-17: TimeField is native TIME, microseconds truncated
- **Decision (project owner):** `TimeField` maps to `TIME`.
  `adapt_timefield_value()` truncates microseconds, so saving and lookups
  (`filter(t=...)`) are consistent with what is stored. Documented in the
  README; Django tests that need sub-second times go into
  `django_test_expected_failures` with the reason "Db2 for i TIME has no
  fractional seconds".
- **Why:** Db2 for i 7.5 `TIME` has no fractional seconds and drops them
  silently (probe `probe_operations`). Native `TIME` keeps interoperability
  with existing IBM i tables (`inspectdb`, legacy `TIME` columns) and native
  time functions.
- **Alternative rejected:** store `TimeField` as `TIMESTAMP(6)` with a fixed
  date, like the Oracle backend (keeps microseconds, but comparisons with
  existing `TIME` columns and time functions need extra handling).
- **Possible future extension (not built):** an opt-in field that stores a
  time with microseconds as `TIMESTAMP`.

## 2026-10-17: sequence_reset_sql restarts identities at MAX(pk) + 1
- **Decision:** `sequence_reset_sql()` queries `COALESCE(MAX(pk), 0) + 1` per
  model with an `AutoField` and emits `ALTER TABLE t ALTER COLUMN pk RESTART
  WITH <n>`.
- **Why:** `GENERATED BY DEFAULT` identities do not advance past explicit
  key values (probe `probe_operations`), so after `loaddata` the next
  generated key would collide; `RESTART WITH` needs a constant.
- **Limit:** a concurrent insert between the query and the `ALTER` is not
  covered (as for other backends' sequence reset during `loaddata`).

## 2026-10-17: Foreign keys use Db2's default NO ACTION
- **Decision (project owner):** foreign keys are created without an
  `ON DELETE` clause (Db2 default `NO ACTION`, checked at the end of the
  statement), never `RESTRICT` (checked per row), so `DELETE FROM` on a
  self-referencing table works during flush. Cycles between tables are out of
  scope for now.

## 2026-10-17: Keep identity columns; defer identity restarts after commit
- **Decision (project owner):** `AutoField`s stay `GENERATED BY DEFAULT AS
  IDENTITY`. Identity restarts (`ALTER TABLE ... RESTART WITH`) run outside
  transactions: `execute_sql_flush()` runs them after its own atomic block,
  and inside an outer atomic block they (and `sequence_reset_sql()`, e.g. in
  `loaddata`) are deferred with `on_commit()`. No second connection is used.
  Every deferral is logged at DEBUG on logger `django_db2_for_i`.
- **Why:** an identity restart in a transaction with pending changes on the
  table fails with SQL0910 (docs/IBMI_NOTES.md).
- **Known gap:** Django's `TestCase` never commits, so deferred restarts never
  run there; a test that loads fixtures with explicit keys and then inserts
  without a key can hit an `IntegrityError`. Such Django tests get the fixed
  reason `"identity restart deferred in TestCase (SQL0910)"`
  (`features.REASON_IDENTITY_RESTART_DEFERRED`). The impact is measured in
  phase 1, step 9.
- **Alternative evaluated, not adopted:** a `SEQUENCE` per table (probe
  `probe_sequence`). `ALTER SEQUENCE ... RESTART` works inside such a
  transaction and `PREVIOUS VALUE FOR` returns an `int`, but
  `DEFAULT NEXT VALUE FOR` is not supported (SQL0199), so every insert would
  need `NEXT VALUE FOR` injected by a custom insert compiler (inserts without
  a key from raw SQL or other applications would fail), each table would get
  an extra `*DTAARA` object to create, rename and drop in migrations and to map
  back in introspection, a rollback does not undo the restart, and `CACHE 20`
  leaves gaps. It also departs from how IBM i tables usually generate keys.
- **Last resort (not probed):** a `BEFORE INSERT` trigger that fills the key
  from a sequence.
- **Step 9 experiment (not built):** start identity columns in the test
  database at a higher value (e.g. 1000) to avoid fixture collisions, and
  measure the net effect, since some Django tests expect specific pk values.

## 2026-10-17: Fixed reason strings for skips and expected failures
- **Decision:** related skips and expected failures share one reason string,
  defined once as a `REASON_*` constant in `features.py`.
  `DatabaseFeatures.expected_failures` maps each reason to its tests;
  `django_test_expected_failures` is the union.
- **Why:** entries can be counted and found per cause (the measure of
  progress), and a fixed string avoids near-duplicate reasons.

## 2026-10-17: Test databases in an existing library, guarded by a marker table
- **Decision:** with `TEST = {"NAME": "<library>", "CREATE_DB": False}` tests
  run in an existing, journaled library; creating test schemas is not
  implemented yet (`NotSupportedError`). Setup and teardown run on the
  alias's own connection; `_nodb_cursor()` always raises. Safety gate
  (project owner):
  - setup checks that the library exists and has an active `QSQJRN` journal;
  - a library without the marker table `DJDB2I_TEST_MARKER` must contain no
    user table or view, otherwise setup refuses, also with `--noinput`
    (it may be a production library, even if it holds only Django tables);
  - setup creates/rewrites the marker: run id, timestamp and a snapshot of
    the tables that belong to the library (empty when it was empty);
  - in a marked library, tables not in the snapshot are leftovers of earlier
    runs: dropped after confirmation or with `--noinput`, reused with
    `--keepdb`;
  - teardown drops everything not in the snapshot (views, then tables
    children first), then the marker; nothing with `--keepdb`; on a failed
    drop the marker stays, so the next run can finish the cleanup;
  - `TEST["NAME"]` equal to `NAME` is allowed (PUB400 has only two libraries)
    but logged as a warning.
- **Why:** PUB400 users cannot create schemas and connections per client are
  limited; the marker makes "is this a test library?" explicit instead of
  guessing from table names.
- **Alternatives:** drop any table of the models under test (rejected: would
  drop production data in a library that holds only Django tables); a
  separate `OPTIONS` flag instead of Django's (Oracle-style) `TEST` keys.
- **pub400 tier:** `nox -s pub400` passes `--reuse-db` (keepdb) by default;
  `nox -s pub400 -- --create-db` runs fully clean.

## 2026-10-17: Ignore system catalog views when listing tables
- **Decision:** introspection and test database creation list only
  `QSYS2.SYSTABLES` rows with `SYSTEM_TABLE = 'N'`.
- **Why:** Db2 for i adds SQL catalog views (`SYSCST`, ...) to a library with
  its first constraint (docs/IBMI_NOTES.md); they are not Django's and must
  never be dropped or reported as foreign objects.

## 2026-10-17: Merge commits instead of rebase merging; signed commits on main
- **Decision (project owner):** pull requests are merged with merge commits
  only (rebase and squash merging off), and the ruleset requires signed
  commits on `main`. Claude still rebases its PR branch onto `main` before
  review; the maintainer never uses "Update branch". History is not
  rewritten.
- **Why:** GitHub's rebase merge recreates the PR commits with the merging
  user as committer and **without signatures**, so the machine account's SSH
  signatures were lost (checked via the API: `verified=false`,
  `reason=unsigned`). With merge commits the PR commits land unchanged, with
  their signatures, and GitHub signs the merge commit.
- **State of the history:** the first 59 commits on `main` are unsigned: the
  initial push (50 commits), four direct pushes made before the ruleset
  existed, and the rebase-merged commits of PR #1 (`89f055f`), PR #2
  (`f5813bd`) and PR #3 (`65ca558`, `16160f6`, `6a7d259`). PR #4 was the first
  pull request merged with a merge commit: its commits (`94ba0fc`, `0a61b88`)
  keep the machine account's signatures and its merge commit `0a17487` is
  signed by GitHub (all Verified). From `0a17487` on, every commit on `main` is
  signed. (Locally, `git log --show-signature` reports GitHub's merge commits as
  unverifiable until GitHub's own signing key is trusted; GitHub shows them as
  Verified.)
- **Tag:** `signing-start` is a signed annotated tag (machine account, Verified)
  on `0a17487`, marking the first signed commit on `main`.
- **Alternatives:** squash merging (GitHub signs the squash commit, but the
  machine account's signatures and the individual commits are lost); keep
  rebase merging (no verifiable signatures on `main`).

## 2026-10-17: Golden file format and verification
- **Decision:** one plain `.sql` file per case under
  `tests/offline/golden/<django>/<profile>/<group>/<name>.sql`, with a comment
  header (`golden`, `django`, `profile`, `depends`, `params` as JSON per
  statement with tagged non-JSON values, `verified`) and the statements in
  execution order. Cases live in `tests/golden_cases.py`; the offline tier
  compares, `--update-goldens` rewrites (refused when `CI` is set), and any SQL
  or params change resets `verified`. The pub400 tier executes the stored
  goldens: safety gate of the test library without migrate, then create, query,
  DML (rolled back), flush (after checking the mocked catalog metadata against
  the real catalog) and drop goldens; `--record-verification` stamps
  "IBM i <release> on PUB400, <date>".
- **Why:** reviewable diffs of the SQL itself; a Django level so phase 3 only
  adds a directory; DDL verified exactly as stored (the tables are created by
  the create goldens themselves, so nothing conflicts with migrate's tables);
  predictable skips through declared dependencies.
- **Meaning of "verified":** accepted by Db2 for i, not correct results.
- **Alternatives:** JSON/YAML files (SQL hard to read and diff); verifying DDL
  with renamed tables (would verify different SQL than the golden).

## 2026-10-17: Typed parameter markers for Value expressions
- **Decision:** every `Value` expression is rendered as `CAST(? AS <type>)`
  (or `CAST(NULL AS <type>)`), through a `Value.as_db2_for_i()` method in
  `django_db2_for_i/expressions.py`, imported by `base.py`. Plain filter
  parameters stay `?`. Type rules: strings without `max_length` get
  `NVARCHAR(<UTF-16 length, at least 1>)`; integers `INTEGER`, `BIGINT` or
  `DECIMAL(n, 0)` by range; decimals without `max_digits` the precision and
  scale of the value; `None` with a known output field a typed NULL, without
  one a plain `NULL`; everything else the field's cast type. One golden per
  rule, all accepted on IBM i 7.5 (PUB400).
- **Why:** Db2 for i rejects untyped parameter markers in the select list,
  `CASE`, `COALESCE` and arithmetic (SQL0418, found by the `exists()` golden);
  `QuerySet.exists()` was unusable.
- **Why `as_<vendor>`:** Django documents monkey patching `as_<vendor>()` onto
  expression classes as the way for third-party backends to change one
  expression's SQL (docs/ref/models/expressions.txt, "Adding support in
  third-party database backends"). It is the smallest change; a custom
  `compiler.py` (overriding `SQLCompiler.compile()` for every compiler class)
  would do the same with more code.
- **Also:** `cast_data_types` maps the AutoFields to plain integer types, since
  their `data_types` carry the identity clause.

## 2026-10-17: Value cast rules: precedence, buckets, maximum, unsupported types
- **Decision:** an explicit `output_field` always wins over the inferred type
  (detected from the expression's constructor arguments); the integer range
  rule applies only to inferred types. Inferred string lengths are rounded up
  to the buckets 32, 256, 1024, 4000, 16370 units, so different value lengths
  share one SQL text. Strings longer than 16370 units are refused with
  `NotSupportedError` instead of a `DBCLOB` cast. Value types without a rule
  (UUID, bytes, timedelta, JSON, ...) raise `NotSupportedError` naming the
  type; their rules come with the field support in later phases. The DB-API
  `Binary` constructor is added (Django's `BinaryField` calls it).
- **Why:** plan cache reuse for statements with string values; 16370 is the
  largest `NVARCHAR` a cast round-trips exactly, above it the server fails
  with SQL0901; a `DBCLOB` cast loses characters from 8185 on (probe
  `string_limits`); an untyped marker or invalid SQL for unknown types would
  fail later and less clearly.
- **Alternatives:** exact lengths (one SQL text per length); `DBCLOB` above
  the maximum (rejected: silent data loss).

## 2026-10-17: Refuse string parameters longer than 8184 UTF-16 units
- **Decision (project owner):** the pyodbc driver refuses every string
  parameter longer than 8184 UTF-16 units with `NotSupportedError`, in
  `execute()` and `executemany()`, before anything is sent. Bytes are not
  limited. The root cause investigation (write path, read path, BLOB) follows
  after phase 1.
- **Why:** string parameters bound as LOB lose characters silently from 8185
  units on (probe `string_limits`); silent data loss must not exist, even
  temporarily. Whether pyodbc binds a parameter as LOB depends on the
  driver's description of the target, which is not visible to the backend, so
  the guard cannot be limited to LOB-bound parameters.
- **Cost:** values of 8185 to 16370 units for `NVARCHAR` targets (which arrive
  intact) are refused as well, including `Value` strings in that range.

## 2026-10-17: Running Django's test suite on PUB400
- **Decision:** `scripts/runtests.sh <version> [--clean] <module>...` runs
  `runtests.py` in the tests container, one call per module, with
  `--parallel=1 --noinput` and `--keepdb` unless `--clean`. It refuses runs
  without modules (the full suite) or with more than three modules, both on
  the host and in the container. Output is scrubbed of `DB2I_PASSWORD` and
  written to `test-results/<version>/<module>.log` with a header (module,
  Django and backend commits, keepdb, start) and footer (exit code, end).
  `scripts/update_test_status.py` generates `docs/TEST_STATUS.md` from the logs,
  the backend's True feature flags, the expected failures/skips per reason and
  the golden status.
- **Two databases:** Django's test settings must define `default` and `other`
  (Django's contributing docs; a test class using an undefined alias fails with
  `ImproperlyConfigured`). `other` is the second PUB400 library, journaled with
  `setup_journal --library other` (approved), guarded by its own marker. It opens
  a second connection only when a selected test uses it. Library names come
  from `.env` only. The pytest pub400 tier keeps using `default` only.
- **Module set in the marker (project owner):** `TEST["MODULE_SET"]` (set per run
  from `DB2I_TEST_MODULES`) is stored in the marker's header row. With `--keepdb`,
  leftovers are reused only for the same module set; for another set they are
  dropped automatically, so tables of different modules do not pile up (1 GB
  quota). A marker written before the column existed is recognised and
  recreated.
- **Alternatives:** `"other": {"TEST": {"MIRROR": "default"}}` (one library, but
  tests that expect separate databases fail); one `runtests.py` call for all
  modules (one log, and keepdb could not tell module sets apart).

## 2026-10-17: Column defaults are bare literals, one rule per type
- **Decision:** `requires_literal_defaults = True` (already set): both Python
  defaults written while a migration adds a NOT NULL column and `db_default`
  go through `DatabaseSchemaEditor.prepare_default()`. `db_default_sql()` no
  longer compiles the `Value` (which gave `CAST(? AS ...)`, rejected with
  SQL0574): it prepares the value like the field's own values and writes a
  literal. Rules: strings as `'...'` (printable ASCII without quotes) or
  `UX'<UTF-16 hex>'` (everything else), booleans `TRUE`/`FALSE`, integers,
  `Decimal` in fixed-point notation, floats with an exponent (`1.5E0`), naive
  date/time/datetime in ISO format, bytes `BX'..'`. `None` means no default:
  `db_default=None` writes no DEFAULT clause. Everything else (aware
  datetimes, NaN/infinity, other types) raises `NotSupportedError`.
- **Why:** Db2 for i accepts only bare constants and special registers in a
  DEFAULT, and stores escaped quotes and non-ASCII constants wrongly (probe
  `probe_defaults`, docs/IBMI_NOTES.md); the UX constant is stored correctly in
  every string column type.
- **Alternatives:** `N'...'` (truncates CHAR values); `'...'` with doubled
  quotes (stores `O''Brien`); refusing strings with quotes (needlessly strict).
- **Later improvement:** `db_default=Now()` could map to the
  `CURRENT_TIMESTAMP` special register (accepted as a DEFAULT); for now
  expression defaults are not supported (`supports_expression_defaults =
  False`).

## 2026-10-17: Date functions run in the database time zone only
- **Decision (project owner):** `DATABASES[alias]["TIME_ZONE"]`
  (`connection.timezone_name`, UTC if not set) is the zone in which Db2 for i
  stores datetimes. Date functions that take `tzname` (`datetime_extract_sql`
  now; trunc and cast when they are implemented) do no conversion when
  `tzname` is None (`USE_TZ = False`) or equals that zone, and raise
  `NotSupportedError` naming both zones otherwise.
- **Why:** there is no time zone aware timestamp type and no time zone
  database on the server side that the backend uses; a fixed-offset
  conversion would be wrong across DST changes.
- **Later:** real conversion (e.g. through a zone table or server function)
  belongs to a later phase (Django's `timezones` tests).
- **Extract functions:** scalar functions (`YEAR`, `WEEK_ISO`, `DAYOFWEEK`,
  `DAYOFWEEK_ISO`, `SECOND`, ...) instead of `EXTRACT`, because
  `EXTRACT(SECOND ...)` returns fractions and `EXTRACT` has no ISO day of the
  week (probe `extract`). ISO year: `INTEGER(VARCHAR_FORMAT(x, 'IYYY'))`
  (one occurrence of the expression, so its parameters are not repeated).
- **Test settings:** the offline and pub400 tiers set `TIME_ZONE = "UTC"`
  (Django's default `America/Chicago` would differ from the database's UTC).

## 2026-10-17: Inquiry message reply as an opt-in connection setting (CPA32B2)
- **Decision (project owner):** `OPTIONS["inquiry_message_reply"]` (`*RQD`,
  `*DFT` or `*SYSRPYL`; default not set). When set, the backend reads the
  job's current `INQMSGRPY` at connect, then runs
  `CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY(<value>)')`, for the whole connection
  (no per-DDL variant); at close it restores the value it read, not a fixed
  `*RQD`. If the original cannot be read, nothing is changed and a
  `DatabaseError` explains why. Without the option the job attribute is never
  touched. Public helpers `set_inquiry_message_reply()` and
  `restore_inquiry_message_reply()` do the same on demand.
- **Error message:** an `ALTER TABLE` that fails with `HY008` while the job
  log shows CPA32B2/CPD32CE is re-raised as `OperationalError` explaining the
  administrator's `ADDRPYLE MSGID(CPA32B2) RPY('I')` and the option.
- **Why:** DROP COLUMN and narrowing column changes send CPA32B2 (default
  reply cancel), also on empty tables. A system reply list entry is the IBM i
  way to answer it; it is system-wide, so it is the administrator's decision,
  and the backend only switches its own job to use it. On PUB400 there is no
  matching entry and none can be added (probe `probe_inquiry`).
- **Alternatives:** changing the attribute only around each ALTER TABLE
  (rejected by the project owner: connection level is simpler and the value is
  restored at close); a QAQQINI option (none exists); rebuilding tables for
  data-losing changes (large; phase 4 only if needed).

## 2026-10-17: Open question for phase 4: table rebuild for data-losing ALTER TABLE
- **Status:** open; decide in phase 4 from the `schema` and `migrations` test
  results (project owner).
- **Question:** CPA32B2 fires for `DROP COLUMN` also on empty tables and for
  every narrowing `ALTER COLUMN` (probe `probe_inquiry`). On systems without a
  system reply list entry (`ADDRPYLE MSGID(CPA32B2) RPY('I')`), such
  migrations fail even with `OPTIONS["inquiry_message_reply"]`. Is a
  table-rebuild fallback needed: create the new table, copy the rows, drop the
  old table, rename (as Django does for SQLite, `_remake_table`)?
- **To weigh:** indexes, constraints, foreign keys pointing at the table,
  views, triggers, authorities and journaling must be recreated; the copy
  costs time and space for large tables; it must not run silently on
  production data.

