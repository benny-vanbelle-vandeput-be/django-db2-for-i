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
*Superseded by "pyodbc maxwrite; string parameters up to 1M UTF-16 units" below.*

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

## 2026-10-17: pyodbc maxwrite; string parameters up to 1M UTF-16 units
- **Decision:** the pyodbc driver sets `Connection.maxwrite` to 4 MiB on every
  connection, and refuses string parameters longer than 1,048,576 UTF-16
  units (`MAX_STRING_PARAM_UNITS`) with `NotSupportedError` before sending.
  Bytes are not limited. Replaces the 8184-unit guard.
- **Why:** root cause of the LOB parameter loss (probe `probe_encoding`,
  docs/IBMI_NOTES.md): pyodbc sends a parameter larger than its limit as
  data-at-execution, in chunks of that limit; without `maxwrite` the limit
  for strings is the driver's `SQL_WVARCHAR` size, 16369, an odd byte count
  that splits UTF-16 units, which the driver drops for LOB targets. With
  `maxwrite` above every accepted string, strings are always bound in one
  buffer; verified on PUB400 for `NCLOB`, `DBCLOB`, `CLOB CCSID 1208` and
  `NVARCHAR` targets, accented and emoji texts, and the maximum itself
  (pub400 tier, `Document` model). 1M units is the capacity of the
  `TextField` column (`NCLOB` = `NCLOB(1M)`). 4 MiB covers that maximum in
  UTF-16 (2 MiB) and in UTF-8 (at most 3 bytes per UTF-16 unit), so the
  limit stays correct if statement encoding moves to UTF-8. Above `maxwrite`
  pyodbc chunks again: harmless for bytes (`BLOB` verified with chunks), not
  for strings, hence the refusal.
- **Alternatives:** `setinputsizes` per parameter (verified: does not avoid
  the chunking); an even `maxwrite` without a string limit (an even chunk
  size can still split a surrogate pair or, in UTF-8, a multi-byte
  character; unverified, so refused); no limit with a much larger
  `maxwrite` (one buffer per value, memory grows with the value; not needed
  for the column types the backend creates).
- **Not changed:** `Value` strings are still limited to `NVARCHAR(16370)`
  casts; a longer cast rule can follow with its own tests.

## 2026-10-17: Statement text and string parameters as UTF-8
- **Decision:** the pyodbc driver calls `setencoding("utf-8", SQL_CHAR)` on
  every connection and sets `UNICODESQL=1` and `CCSID=1208` (reserved, not
  overridable). Reading keeps pyodbc's defaults (UTF-16). The schema
  editor's `quote_value()` writes strings as plain `'...'` constants with
  doubled quotes; column defaults keep `UX'...'` (`default_literal()`).
- **Why:** with the backend's settings (pyodbc pooling off), the driver's
  wide-character statement functions silently convert statement text to the
  job CCSID (273 on PUB400), so `€` and emoji in SQL text were lost (probe
  `probe_encoding`, docs/IBMI_NOTES.md; with pooling on, the same calls fail
  with HY001). Only the narrow functions with UTF-8, `UNICODESQL=1` (the
  statement reaches the server as Unicode) and `CCSID=1208` (the client code
  page no longer depends on the process locale) carry every character,
  emoji included; verified for literals, comments, aliases, parameters into
  every column type, reading, result column names and error messages. Plain
  string constants are needed for `COMMENT ON`, which rejects `UX'...'`.
- **Alternatives:** `UNICODESQL=1` alone on the wide-character path (simpler,
  parameters stay UTF-16; rejected: characters outside the BMP, such as
  emoji, are still garbled silently); keeping `UX'...'` everywhere (rejected:
  `COMMENT ON` refuses it).
- **Limits found on the way** (server rules, not fixable on the client):
  names and `COMMENT ON` text must use characters of the job CCSID
  (SQL0104); `VARCHAR`/`CHAR` columns in the job CCSID refuse other
  characters (22018). Result column names and error messages need a UTF-8
  process locale.

## 2026-10-18: Releases from OpenPGP-signed tags, GitHub pre-releases only
- **Decision (project owner):** alpha releases are GitHub pre-releases (sdist
  and wheel), not PyPI. Only the maintainer creates release tags, signed with
  their OpenPGP (GPG) key in their own release clone. The release workflow
  (`.github/workflows/release.yml`) refuses a tag that is unannotated,
  unsigned, signed by another key, not on `main`, not `v` + `__version__`,
  or without a CHANGELOG section (`scripts/verify_release_tag.py`). The
  public key is stored ASCII-armored in the admin-only Actions variable
  `RELEASE_SIGNING_KEY`, not in the repository. `__version__` in
  `django_db2_for_i/__init__.py` is the single version source (hatch reads
  it). Before publishing, the offline tier runs against the installed wheel
  (`nox -s wheel`), from a copy of the tests without the source package.
- **Why:** a release is created only from a commit the maintainer signed off
  on, and a pull request cannot change the trusted key (a key file in the
  repository could be replaced in the same PR as the workflow); testing the
  wheel catches packaging mistakes (missing modules or files) that tests
  against the source tree cannot.
- **Verification details:** the key is imported into an empty, temporary
  GnuPG home; the signature must produce `GOODSIG` and a `VALIDSIG` whose
  primary key fingerprint is the imported key's; `BADSIG`, `ERRSIG`,
  `EXPSIG`, `EXPKEYSIG`, `REVKEYSIG` and `NO_PUBKEY` are refused. A variable
  with a secret key or more than one key is refused.
- **Not changed:** the existing `v0.1.0a1` tag (made before this workflow;
  its code reports `0.0.1.dev0`) is not moved or recreated.

## 2026-10-18: DISTINCT with emulated NULL ordering: hidden columns, ORDER BY position
- **Decision (project owner approved the approach):** the backend uses its own
  compiler module (`compiler.py`; insert/update/delete/aggregate compilers
  are Django's combined with it). For `SELECT DISTINCT` queries whose
  ordering uses Django's NULL ordering emulation (`<expr> IS [NOT] NULL,
  <expr>`), `SQLCompiler.get_extra_select()` selects the predicate (as an
  `IsNull` lookup, so GROUP BY treats aggregates correctly) and the
  expression as hidden columns, and `pre_sql_setup()` replaces that ORDER BY
  entry with their positions (`ORDER BY 4 ASC, 3 DESC`).
- **Why:** Db2 for i has no `NULLS FIRST/LAST` (SQL0199). With DISTINCT,
  every ORDER BY expression must be in the select list (SQL0214), and an
  expression containing parameter markers never matches a selected one,
  even with identical text (typed or untyped markers); select-list
  positions always match. Hidden columns are trimmed from results by Django
  (`has_extra_select`); the predicate depends only on a selected
  expression, so DISTINCT returns the same rows. Verified by Django's
  `ordering` test and a pub400 test (duplicates, NULLs, a parameter in the
  subquery; model instances, `values()`, `values_list()`).
- **Alternatives:** repeating the expressions in ORDER BY (fails with
  parameters); an expected failure (`REASON_DISTINCT_ORDER_BY`); ordering by
  `CASE` (same SQL0214 under DISTINCT).

## 2026-10-18: Exists() by context, predicates in the select list
- **Decision (project owner approved C1):** `supports_boolean_expr_in_select_clause
  = True`. `compiler.py` renders `Exists()` as `EXISTS (...)` only when it is
  a search condition of the query's WHERE / HAVING / QUALIFY (directly, in
  nested AND/OR, under `NOT`, or as Django's `Exact(<condition>, True)`
  form of `filter(<condition>)`); everywhere else as `((<subquery>) IS NOT
  NULL)`. The Exists subquery always selects a literal `1`.
- **Why:** Db2 for i rejects `EXISTS` outside a search condition, also in
  `CASE WHEN` inside WHERE, and in ORDER BY (SQL0104 / SQL0115); a
  parameter marker in the select list of an EXISTS subquery fails in the
  host server (30187). Django's Exists subquery is `SELECT 1 ... FETCH
  FIRST 1 ROWS ONLY`, so the scalar form stops at the first row like EXISTS
  (preferred by the project owner over `COUNT(*) > 0`); EXISTS stays where
  it is valid, because the optimizer handles it best there. Predicates are
  valid in the select list and GROUP BY on 7.5; with the flag off, Django
  returned `CASE ... THEN 1 ELSE 0` integers, which cannot be compared with
  BOOLEAN values.
- **Context tracking:** `SQLCompiler.compile()` keeps a flag; a `WhereNode`
  is a condition only if it is the query's WHERE / HAVING / QUALIFY (by
  identity) or nested in one, so `Q` annotations and conditions inside
  `When` or lookups get the scalar form.
- **Alternatives:** the scalar form everywhere (simpler, but drops EXISTS
  where the optimizer handles it best); `CASE WHEN (SELECT COUNT(*) ...) > 0`
  (counts every row).

## 2026-10-18: Predicates as comparison operands
- **Decision (project owner approved C2):** `Lookup.as_db2_for_i`
  (`expressions.py`) wraps an operand in `CASE WHEN <predicate> THEN TRUE
  ELSE FALSE END` only when both operands of the lookup are conditional and
  that operand renders as a predicate (a lookup, `Q` / WhereNode, `Exists`,
  or an ExpressionWrapper / NegatedExpression around one). Boolean columns
  and values stay as they are; `filter(<cond>=True)`, which Django renders
  as just the condition, is unchanged, and so are all earlier goldens.
- **Why:** Db2 for i rejects a predicate as a comparison operand (SQL0104,
  probe `queries`); the CASE form is a BOOLEAN value and works on either
  side. Django's Oracle backend does the same in `Lookup.as_oracle`, but
  that also wraps boolean columns (for us every conditional expression is
  valid in WHERE), which would change existing SQL.
- **Alternatives:** wrapping every conditional operand (changes the SQL of
  plain boolean column comparisons); comparing via `IS TRUE` forms (not
  valid either).

## 2026-10-18: Predicates as select columns: CASE WHEN ... THEN TRUE ELSE FALSE END
- **Decision (project owner approved):** a lookup or `Q` (or a wrapper
  around one) compiled directly by the compiler (a select column, a GROUP BY
  item, an UPDATE value) is written as `CASE WHEN <predicate> THEN TRUE ELSE
  FALSE END`. Nested predicates, search conditions and `Exists()` are not
  wrapped. `supports_boolean_expr_in_select_clause` stays on.
- **Why:** a regression from enabling the flag (C1): `SELECT X < ?` with an
  untyped marker fails with SQL0418, which broke selected `Q` / lookup
  annotations with plain values (found by an own pub400 test; Django's
  tests select such annotations only through `values_list()` on other
  columns). The CASE form accepts untyped markers and still returns
  BOOLEAN, which was the reason for C1. Two goldens change to the CASE form
  (`expressions/annotate_lookup`, `queries/filter_lookup_operands`, which
  selects its annotation).
- **Not fixed:** GROUP BY an expression with parameter markers (30101,
  markers never match); documented in Known Limitations, with a strict
  expected failure in the pub400 tier.
- **Alternatives:** casting the markers of select-list lookups (changes the
  SQL of every lookup with a value); turning the flag off again (1/0
  integers that cannot be compared with BOOLEAN).

## 2026-10-18: Never compare two untyped parameter markers
- **Rule:** the backend never emits a comparison with untyped parameter
  markers on both sides. Values in expressions are typed markers
  (`CAST(? AS <type>)`, expressions.py), so `GreaterThan(2, 1)` becomes
  `CAST(? AS INTEGER) > CAST(? AS INTEGER)`.
- **Why:** Db2 for i accepts `WHERE ? > ?` with two untyped markers but
  returns a wrong result, silently (no row for 2 > 1; probe `queries`). A
  silent wrong result is worse than an error.
- **Guards:** `tests/offline/test_typed_markers.py` scans every golden and a
  set of compiled comparisons (direct values, two `Value`s, strings, a
  `Value` against a `Q`, annotations) for `%s <op> %s` with two bare
  markers; a pub400 test checks that `2 > 1` is true and `1 > 2` false.
- **Consequence:** Django's `lookup.tests.LookupTests.test_lookup_direct_value_rhs_unwrapped`
  asserts the SQL text `2 > 1` and is an expected failure
  (`REASON_TYPED_PARAMETER_MARKERS`). `test_exact_none_transform` uses a
  custom transform with the template `NULL` (`WHERE NULL IS NULL`, SQL0206)
  and is an expected failure (`REASON_UNTYPED_NULL`).


## 2026-10-18: Avg of an integer: cast the argument to DOUBLE
- **Decision (project owner approved):** when `Avg`'s output is a FloatField
  (an integer argument) and its argument is not a FloatField, the argument is
  cast to DOUBLE: `AVG(CAST(x AS DOUBLE))`. `Avg` over a DecimalField or
  FloatField is unchanged.
- **Why:** Db2 for i returns `AVG` of INTEGER as INTEGER (truncated; probe
  `queries`), Django expects a float. `AVG` of DECIMAL(5, 2) is an exact
  DECIMAL(31, 28), so a cast there would only lose precision.
- **Alternatives:** casting the result (`DOUBLE(AVG(x))`, already truncated);
  casting every argument to DOUBLE (loses DECIMAL precision).

## 2026-10-18: StringAgg as LISTAGG of an NCLOB, NULL through CASE
- **Decision:** `StringAgg` is written as `CASE WHEN COUNT(<expr>) = 0 THEN
  NULL ELSE LISTAGG(CAST(<expr> AS NCLOB), CAST(? AS NVARCHAR(32))) END`
  (no cast when the argument is an NCLOB already). The separator is the
  typed marker of its `Value`.
- **Why:** `LISTAGG` of an NVARCHAR (our CharField) is limited to 2000
  characters and of a VARCHAR to 4000 bytes; a longer result fails (SQL0802,
  probe `listagg`). With an NCLOB argument the limit is 1M characters, and
  `StringAgg` is a TextField (NCLOB on this backend) anyway. An untyped
  separator constant fails with NCLOB arguments of 8K and longer. The CASE
  is needed because the ODBC driver returns a NULL `LISTAGG` result (no
  values) as an empty string; it keeps a real empty string, unlike
  `NULLIF(LISTAGG(...), '')`.
- **Alternatives:** the argument as it is (2000 character limit for
  CharFields); `ON OVERFLOW TRUNCATE` (silently cut results); `NULLIF`
  (turns a real empty string into NULL).

## 2026-10-18: Changelog fragments; golden cases and pub400 tests split by area
- **Decision (project owner asked for it):** pull requests no longer edit
  `CHANGELOG.md`; each adds `changelog.d/<PR number or topic>.<type>.md`
  (types added, enabled, changed, fixed, limitation), and the release PR
  assembles them with `scripts/assemble_changelog.py release <version>`.
  `tests/golden_cases.py` became the package `tests/golden_cases/` with one
  module per golden group; the pub400 `test_schema.py` was split into
  `test_schema.py`, `test_queries.py` and `test_aggregates.py`, which share
  the `testapp_tables` fixture (conftest.py).
- **Why:** almost every parallel pull request conflicted in the Unreleased
  section of CHANGELOG.md and at the end of the same two test files, which
  cost a rebase and a pub400 run per merge.
- **Consequence:** the testapp tables are created once per pub400 module
  (three times per tier run instead of once, about 20 s more), and each
  module starts with fresh tables.
- **Alternatives:** towncrier (an extra dependency and template for what a
  100-line script does; the script also keeps the "Enabled features"
  heading and the compare links of this CHANGELOG); one package-scoped
  table fixture (the golden verification creates the same tables in
  between).

## 2026-10-18: Ordered UNION queries wrapped in SELECT * FROM LATERAL (...)
- **Decision:** `supports_select_union` and
  `requires_compound_order_by_subquery` are on; the compiler writes Django's
  wrapper of an ordered compound query as `SELECT * FROM LATERAL
  (<compound>) ORDER BY ...` instead of `SELECT * FROM (<compound>)`.
- **Why:** the ORDER BY of a compound query accepts no expressions (SQL0214),
  and Django's NULL ordering emulation is one; wrapped, any ORDER BY works.
  A plain nested table expression inside a correlated subquery cannot see
  the outer table (SQL5001 / SQL0204, Django's
  `test_union_in_subquery_related_outerref`); `LATERAL` can, and works
  uncorrelated as well (probe `queries`).
- **Alternatives:** wrapping only when the ORDER BY has expressions (the
  flag is global, and the compiler would have to re-render Django's
  ordering); ordering by positions of hidden columns (a UNION selects no
  extra columns); leaving NULL ordering on unions unsupported.

## 2026-10-18: StringAgg ordering: WITHIN GROUP, NULL rank as a CASE sort key
- **Decision:** `supports_aggregate_order_by_clause` is on.
  `StringAgg(order_by=...)` is written as `LISTAGG(...) WITHIN GROUP (ORDER
  BY ...)` (Oracle's form). An item with `nulls_first` / `nulls_last` is
  ordered by `CASE WHEN <expr> IS NULL THEN 0 ELSE 1 END` (1 / 0 for
  nulls_last) first, then by the expression.
- **Why:** Django's NULL ordering emulation puts a predicate in the ORDER BY,
  which Db2 for i accepts in a query's ORDER BY but not inside WITHIN GROUP
  (SQL0199, probe `listagg`).
- **Alternatives:** leaving nulls_first / nulls_last unsupported in
  aggregates; changing the emulation for every ORDER BY (the query-level
  form works, and the DISTINCT handling in compiler.py relies on it).

## 2026-10-18: GROUP BY expressions with values through a LATERAL grouping table
- **Decision (project owner approved the derived-table option):** when a
  grouped expression (from `values().annotate()`, or a selected
  non-aggregate next to aggregates) has parameters or is nested in another
  selected expression, the compiler computes it per row in `CROSS JOIN
  LATERAL (SELECT <expr> AS "G1", ... FROM SYSIBM.SYSDUMMY1) AS
  "DJDB2I_GROUPING"` and every use of the expression (select list, GROUP BY,
  HAVING, ORDER BY, WHERE) becomes `"DJDB2I_GROUPING"."G<n>"`. Grouping by
  columns, and by expressions without parameters that are only selected as
  a whole, keeps its SQL.
- **Why:** Db2 for i never matches a grouped expression with a parameter
  marker (30101) or a grouped expression nested in a select expression
  (SQL0122), and allows no GROUP BY alias or position (probe `queries`).
  Grouping by a computed value is common in reports. The LATERAL table is
  the derived-table option in its smallest form: the outer query keeps its
  joins, WHERE, aggregates, HAVING and ORDER BY unchanged, and only the
  grouped values move into the derived table, so no other column has to be
  carried through it.
- **Replaces:** the "Not fixed" note of the select-list predicate decision;
  the pub400 xfail and Django's two `REASON_GROUP_BY_MARKERS` expected
  failures (`test_group_by_subquery_annotation`,
  `test_group_by_exists_annotation`), which pass now.
- **Alternatives:** inline literals for numeric and boolean values (fail for
  nested use even without markers; would put literals in the SQL); a full
  derived table of the whole FROM/WHERE (every column used by aggregates,
  HAVING and ORDER BY, including joined tables, would have to be selected
  and renamed through it).
