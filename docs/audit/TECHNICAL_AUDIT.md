# Technical audit: django-db2-for-i (Phase A, audit only)

> **Status of this document.** Written on 2026-11-16 by an independent Claude
> instance that had no context from earlier work on the project, offline only
> (no IBM i connection), on `main` at `c6c60d7`. Its findings are not reviewed yet: a finding marked as a hypothesis is not confirmed by a probe, and a verified one is verified by reading code, not by a run. It is kept here as
> written; later changes to the project are not reflected in it.

- **Commit audited:** `c6c60d7` (main, merge of #269), version `0.1.0b4`
- **Date:** 2026-11-16
- **Scope:** the backend package `django_db2_for_i/` (8,448 lines), its driver
  layer, tests (`tests/offline`, `tests/ibmi`, replay, goldens), probes, CI
  workflows, packaging, and the user and developer documentation.
- **Method:** reading only. No connection to PUB400 or any IBM i was made, no
  test was run, and no code was changed. Django 5.2, 6.0 and 6.1 sources in
  `vendor/` were read to check backend contracts.

## 0. How to read this report

Every finding carries a **status**:

| Status | Meaning |
|---|---|
| **Verified (code)** | Follows directly from the code or configuration in this commit. |
| **Verified (probe)** | Backed by a probe result or IBM i test already in the repository (named). |
| **Hypothesis** | Plausible from IBM documentation or reasoning, not backed by a probe here. The `qtemp_` probe that would settle it is named; a probe needing two jobs or a library is marked `lib_` (needs the maintainer's approval link) or "dedicated IBM i". |
| **Unverified claim** | A statement in the project's own documentation that no probe or test in the repository backs. |

Severities: **Critical** (silent data loss or corruption in the default
configuration, verified), **High** (silent wrong data or unsafe behaviour that a
realistic configuration reaches), **Medium** (wrong or surprising behaviour with
a visible error, operational risk, or a test gap that hides defects), **Low**
(edge cases, maintainability, documentation).

No finding is rated Critical: none of the silent-data findings is both verified
and reachable in the default configuration. Four High findings need a probe or
a decision before they can be closed.

## 1. Summary

The project is unusually disciplined for a pre-1.0 backend: three clean axes
(Django version, driver, server), fail-closed classification of changes, golden
SQL with verification stamps, a replay corpus of passing Django statements,
probes for most IBM i claims, explicit reasons for every skip and expected
failure, and no automatic retries anywhere. 3,475 Django tests pass on 6.1
against PUB400 with 0 failures (TEST_STATUS, 2026-11-14).

The main risks are not in the SQL the backend generates for the tested
patterns, but at the edges the tests do not reach:

1. **Time:** `Now()` is rendered as `CURRENT_TIMESTAMP`, which on IBM i is the
   job's local time, not the connection time zone the backend stores
   datetimes in (F-01).
2. **Configuration accepted without its consequences:** `isolation_level="*NONE"`
   turns transactions off while the features still claim them (F-02);
   `driver_attributes` can override connection keywords the backend's
   correctness depends on (F-09).
3. **Test isolation on a shared system:** models in another library run their
   tests against that library, outside the test library's safety checks (F-03).
4. **Silent values:** data mapping errors become NULL in select lists
   (verified); whether `UPDATE` then writes NULL is claimed in the docs but not
   probed (F-04); trailing blanks compare equal (F-05).
5. **Coverage:** the Django suite runs 31 modules (with `model_fields` limited
   to its JSONField label) and with the non-default `column_rename="copy"`; the
   `backends`, `transaction_hooks`, `fixtures`, `model_fields`, `cache` and
   similar modules that exercise backend contracts are not measured (F-13).

The README's "Beta, not for production" label is accurate. A production
readiness claim would need at least F-01 to F-05 resolved and the module gaps of
F-13 measured.

## 2. Repository discovery

### 2.1 Supported versions (as declared)

| Axis | Declared | Where |
|---|---|---|
| Django | 5.2 LTS (>= 5.2.12), 6.0 (>= 6.0.3), 6.1 | `pyproject.toml`, `compat.py`, `docs/DJANGO_VERSIONS.md` |
| Python | 3.12, 3.13, 3.14; 3.15 with Django >= 6.1.3 | `pyproject.toml` (environment marker), noxfile |
| IBM i | 7.5 minimum (only profile); newer releases fall back to the 7.5 profile with a warning | `capabilities.py` |
| Driver | pyodbc >= 5.3 + IBM i Access ODBC Driver (probed: 07.01.029) | `drivers/pyodbc.py`, `docs/IBMI_NOTES.md` |
| Test system | PUB400 (shared, IBM i 7.5, TR and PTF levels not readable) | CLAUDE.md, TEST_STATUS |

These are consistent across `pyproject.toml`, `compat.py`, CLAUDE.md and README.

### 2.2 Test infrastructure

| Set | Size (6.1) | Runs | Notes |
|---|---|---|---|
| Offline tests | 3,654 passed | CI, every push | Goldens (2.7 MB), DDL collection, unit tests; a fixture fails on any connection attempt. |
| Replay tests | 6,193 statements | CI, every push | Recorded SQL of passing Django tests, compiled again offline (9.9 MB corpus). |
| IBM i tests | 452 passed (about 205 test functions, some parametrized) | Per PR classification, on PUB400 | Includes 7 two-connection row-lock tests. |
| Django suite on IBM i | 3,475 passed, 281 skipped, 71 xfail, 0 failed | Status run before release | 31 module entries; `queries` as 10 labels; `model_fields` = `test_jsonfield` only. |

CI (`.github/workflows/offline.yml`) runs lint, the verification gate, the
offline tests and the replay for every Python x Django combination from the
noxfile. It never connects to an IBM i. The IBM i gate
(`ibmi-gate.yml`, `pull_request_target`) runs main's scripts only and checks
out no PR code: the design is sound.

### 2.3 Backend API map (Django 6.1 contracts)

| Component | File | Notes |
|---|---|---|
| DatabaseWrapper | `base.py` | Connection, `FormatStyleCursor` (`%s` / `%(name)s` to `?`), commitment control, `LOCK TABLE` release via SQL `COMMIT`/`ROLLBACK`, CPA32B2 suppression, `is_usable`. No `_nodb_cursor`. |
| Driver | `drivers/base.py`, `drivers/pyodbc.py` | DB-API exceptions, SQLSTATE/SQLCODE mapping, secret redaction, connection string, `maxwrite`, int64 overflow to Decimal, SQL0443/SQL0519 poisoning. |
| DatabaseFeatures | `features.py` | Optional flags off unless backed by tests and probes, each with a reason (`docs/features.toml`); 26 skip/xfail reasons. |
| DatabaseOperations | `operations.py` | Quoting (uppercase), pagination, date functions (no tz conversion), durations (BIGINT microseconds), flush with FK ordering, identity restarts deferred on SQL0910. |
| Compiler | `compiler.py` | FINAL TABLE returning, MERGE for conflicts, EXISTS/IN rewrites outside search conditions, LATERAL grouping, DISTINCT + null ordering, `FOR UPDATE WITH RS`. |
| Expressions | `expressions.py` (1,547 lines) | Typed markers (`CAST(? AS ...)`), JSON via `JSON_QUERY/JSON_VALUE/JSON_EXISTS`, function overrides. All vendor hooks delegate to `self.as_sql`, so user subclasses keep their own SQL. |
| SchemaEditor | `schema.py`, `column_copy.py`, `inquiry.py` | Literal defaults, combined ALTER clauses, narrowing pre-checks, `LOCK TABLE` before checks, other-library qualification, system names, opt-in column copy. |
| Introspection | `introspection.py` | `QSYS2` catalog, current schema or the table's library; enforced-FK detection. |
| Creation | `creation.py` | Existing-library mode only, marker table, snapshot, journaling checks. |
| Client | `client.py` | Not implemented (`executable_name = None`). |
| Validation | `validation.py` | System checks E001-E006, W001-W003. |

## 3. Strengths (verified)

- **Architecture axes are enforced by tests** (`tests/offline/test_axes.py`):
  no `django.VERSION` outside `compat.py`, no release checks outside
  `capabilities.py`, no driver code outside `drivers/`.
- **Parameter binding everywhere.** All values reach the driver as parameters
  except DDL defaults, which go through `default_literal()` (strings with a
  quote or non-ASCII become `UX'<hex>'`), and a few validated system names
  (`creation._SYSTEM_NAME`, `fields.SYSTEM_NAME`, `inquiry._JOB_NAME`).
  `quote_name` doubles embedded quotes. No SQL injection path was found.
- **Secrets.** `ConnectionParams.password` has `repr=False`; `Secrets` hides
  itself in tracebacks; driver errors are re-raised outside the `except`
  block so the native exception (which could carry the connection string) is
  neither cause nor context; `redact()` strips the password and the
  "Password length" of CWBSY0002. The connection string is built inside
  `_connect()` and never stored.
- **No retries, no silent reconnects.** The driver never reconnects; the
  wrapper marks a connection unusable on SQL0443 (with parameters) and SQL0519
  and lets Django replace it. No duplicate-write path from retries exists.
- **Transactions.** `TRUEAUTOCOMMIT=1` makes autocommit statements atomic
  (probe `lib_autocommit`); savepoints with `ON ROLLBACK RETAIN CURSORS`;
  `can_rollback_ddl` backed by probe `lib_rollback_ddl`; the `LOCK TABLE`
  that survives the driver's `COMMIT HOLD` is released with an SQL `COMMIT`,
  and a failed `ROLLBACK` closes the connection (#162, #241).
- **Migration safety.** Type changes Db2 for i cannot do in place are refused
  before any statement (`converts_in_place`); narrowing that would change a
  value is refused after a `LOCK TABLE` (`narrowing_check`); a NOT NULL column
  without default on a table with rows is refused; CPA32B2 is suppressed only
  inside field changes and turned back on, closing the connection if that
  fails (`end_cpa32b2_suppression`).
- **Encoding.** UTF-8 statement text with `UNICODESQL=1` and `CCSID=1208`,
  locked against override; a locale warning for garbled metadata; long strings
  bound in one buffer below a 1M-unit limit (probe `qtemp_encoding`).
- **Test-library safety.** A library without the marker table and with any
  table is refused, also with `--noinput`; only tables outside the snapshot are
  dropped; journaling is checked first.
- **Every skip and expected failure has a fixed reason string**, and the
  per-version differences are isolated in `compat.py`.

## 4. Findings

Ordered by severity, then by area. Reproduction steps that need an IBM i are
written for a dedicated system or as `qtemp_` probes (job-scoped, allowed on
PUB400 without approval).

---

### F-01 `Now()` returns the IBM i job's local time, not the connection time zone

- **Severity:** High
- **Status:** Hypothesis (strong: IBM documents `CURRENT TIMESTAMP` as the job's
  local time; nothing in the repository converts it)
- **Files:** `operations.py` (no `Now` handling), `expressions.py` (no
  `Now.as_db2_for_i`); Django's `Now.template = "CURRENT_TIMESTAMP"`
  (`django/db/models/functions/datetime.py:214`).
- **Problem:** The backend stores datetimes naive in the connection's time
  zone (UTC unless `DATABASES[...]["TIME_ZONE"]` is set; `operations.py`
  docstring, `adapt_datetimefield_value`). `Now()` renders Django's default
  `CURRENT_TIMESTAMP`, which on Db2 for i is the job's local time (system
  value `QTIMZON` or the job's `TIMZON`). Django's other backends make `Now()`
  agree with the stored values (PostgreSQL `STATEMENT_TIMESTAMP()` as
  `timestamptz`; MySQL after `SET time_zone`; Oracle `LOCALTIMESTAMP` in the
  session zone Django sets).
- **Evidence:** `grep -n "Now\|CURRENT_TIMESTAMP"` finds no override in
  `django_db2_for_i/`; no IBM i test compares `Now()` with `timezone.now()`.
  The Django suite runs with `USE_TZ = False` and `Now()` tests compare only
  relative to other `Now()` values, so the skew is invisible there.
- **Reproduction (dedicated IBM i or PUB400, read-only):**
  `SELECT CURRENT TIMESTAMP, CURRENT TIMEZONE FROM SYSIBM.SYSDUMMY1` against
  the client's UTC clock; then, with `USE_TZ = True` and no database
  `TIME_ZONE`: `obj.updated = Now(); obj.save(); obj.refresh_from_db()` and
  compare with `timezone.now()`.
- **Impact:** `update(modified=Now())`, `filter(expires__lt=Now())` and every
  query that mixes `Now()` with stored values are off by the server's UTC
  offset (one or two hours on a European system such as PUB400). Silent wrong
  data written by `update()`.
- **Recommended correction:** `Now.as_db2_for_i`: when the connection's zone
  is UTC, `CURRENT TIMESTAMP - CURRENT TIMEZONE`; when it equals the job's zone,
  `CURRENT TIMESTAMP`; otherwise refuse (as `_check_tzname` does) or document.
  `CURRENT TIMEZONE` is a decimal duration; verify the DST behaviour.
- **Required tests:** probe `qtemp_current_timestamp_zone` (read-only); an IBM
  i test with `USE_TZ = True` asserting `abs(Now() - timezone.now()) < 1 min`
  after a save; an offline golden for `Now()`.

---

### F-02 `isolation_level="*NONE"` (and `*CHG`) accepted while transactions are reported as supported

- **Severity:** High (configuration-dependent; documented as an allowed value)
- **Status:** Verified (code); runtime behaviour Hypothesis
- **Files:** `drivers/base.py` (`ISOLATION_LEVELS`, `_ISOLATION_ALIASES`),
  `drivers/pyodbc.py` (`COMMIT_MODES["*NONE"] = "0"`), `features.py`
  (`supports_transactions = True`, `uses_savepoints = True`, both fixed),
  `docs/user/Configuration.md` line 29 ("Only `*CS` has been tested").
- **Problem:** With `CMT=0` there is no commitment control: `transaction.atomic()`
  cannot roll anything back, savepoints fail or do nothing, and `TRUEAUTOCOMMIT`
  has no effect. The backend still tells Django that transactions and savepoints
  work, so an exception inside `atomic()` leaves partial writes committed with no
  error. `*CHG` (uncommitted read) silently allows dirty reads.
- **Evidence:** the values are accepted by `normalize_isolation_level()` and
  passed straight to `CMT`; nothing in `features.py` depends on the level.
- **Reproduction (probe):** `qtemp_cmt_none`: a QTEMP table, `CMT=0`,
  autocommit off, `INSERT`, `ROLLBACK`, `SELECT COUNT(*)`; then `SAVEPOINT`.
- **Impact:** silent partial writes and broken `get_or_create`/`atomic`
  semantics for anyone who picks `*NONE` (a common choice on IBM i for
  unjournaled libraries).
- **Recommended correction:** refuse `*NONE` with `ImproperlyConfigured` (or make
  `supports_transactions`/`uses_savepoints` follow the level and warn loudly);
  require an explicit opt-in for `*CHG`, `*ALL`, `*RR` until tested.
- **Required tests:** offline tests of `get_connection_params()` for each level;
  probe above.

---

### F-03 Tests run against tables in other libraries, outside the test library's safety checks

- **Severity:** High (operational safety on shared and production systems)
- **Status:** Verified (code and docs)
- **Files:** `creation.py` (`_create_test_db`, `_destroy_test_db` look only at
  `TEST["NAME"]`), `introspection.py` (`get_table_list` lists the current
  schema only), `apps.py` (`db_library`), `docs/user/Known-Limitations.md`
  "Tables in another library" ("Tests use the same library").
- **Problem:** A model with `Meta.db_library = "SALES"` or
  `db_table = 'SALES"."T'` keeps that library under the test runner. Test setup
  migrates into `SALES`, `TransactionTestCase` flushes only `TEST["NAME"]`, and
  teardown drops only `TEST["NAME"]`'s tables. For unmanaged models over
  existing IBM i files (the typical use of `db_library`), tests read and write
  the real library; `TransactionTestCase` and `LiveServerTestCase` commit those
  writes.
- **Evidence:** docs state it; no code path compares a model's library with the
  test library.
- **Impact:** test runs writing into production libraries; leftovers not
  cleaned up; the marker-table protection gives a false sense of safety.
- **Recommended correction:** at `_create_test_db`, collect the libraries of all
  models; refuse unless each is mapped (e.g. `TEST["LIBRARIES"] = {"SALES":
  "SALESTST"}`, applied by `quote_name`/`split_table` under test) or explicitly
  allowed and itself marked as a test library.
- **Required tests:** offline tests of the refusal; an IBM i test with a model in
  the `other` library.

---

### F-04 Data mapping errors give NULL silently; whether `UPDATE` writes that NULL is not verified

- **Severity:** High if `UPDATE` writes NULL (documented as such); Medium for
  select lists (verified, documented)
- **Status:** Verified (probe) for select lists: probes `qtemp_mapping_errors`,
  `qtemp_durations` (`docs/IBMI_NOTES.md` "Data mapping errors in the select
  list", "Durations"). **Unverified claim** for UPDATE:
  `Known-Limitations.md` "Durations" says "In an update this **writes NULL**";
  both probes are read-only `SELECT`s from `SYSDUMMY1`, and
  `tests/ibmi/test_durations.py` has no such test.
- **Files:** `expressions.py` (`duration_expression_as_db2_for_i`),
  `operations.py`, the docs above.
- **Problem:** `CAST('abc' AS INTEGER)`, division by zero and timestamp
  arithmetic past year 9999 return NULL in a select list with no warning
  (`cursor.messages` empty). If the same holds in `UPDATE ... SET`, then
  `update(deadline=F("deadline") + timedelta(days=30))` replaces values with
  NULL on nullable columns.
- **Reproduction (probe):** `qtemp_update_mapping_errors`: a QTEMP table
  (`CMT=0`) with a TIMESTAMP near 9999-12-31 and an INTEGER;
  `UPDATE ... SET TS = TS + 30 DAYS`, `SET I = CAST('abc' AS INTEGER)`,
  `SET I = I / 0`, `INSERT ... SELECT` of the same; record values or SQLCODEs.
- **Impact:** silent data loss in bulk updates (if confirmed); silent NULLs in
  reports and annotations (confirmed).
- **Recommended correction:** after the probe: either correct the docs, or guard
  duration arithmetic in `UPDATE` (e.g. `CASE WHEN <out of range> THEN
  RAISE_ERROR('22008', ...) ELSE ... END`; verify `RAISE_ERROR` on 7.5), and
  investigate whether a job or QAQQINI option makes data mapping errors in
  select lists raise (document the answer either way).
- **Required tests:** the probe; an IBM i test for the duration UPDATE case.

---

### F-05 Trailing blanks are ignored in string comparisons, unique keys and grouping

- **Severity:** Medium
- **Status:** Hypothesis (Db2 for i SQL reference: in a comparison the shorter
  string is padded with blanks; applies to VARCHAR/NVARCHAR, not to `LIKE`)
- **Files:** `base.py` (`CharField` is `NVARCHAR`), `operators["exact"]`;
  `Known-Limitations.md` "inspectdb and existing IBM i tables" ("Django's own
  `CharField` columns are `NVARCHAR` and not padded").
- **Problem:** `'abc' = 'abc '` is true on Db2 for i. So `filter(code="abc")`
  matches `"abc  "`, `get()` can raise `MultipleObjectsReturned`, a `unique`
  `CharField` refuses `"abc "` next to `"abc"` (IntegrityError where PostgreSQL
  accepts it), and `distinct()` / `GROUP BY` merge them. The docs mention the
  padding only for `CHAR` columns of existing tables.
- **Reproduction (probe):** `qtemp_trailing_blanks`: `NVARCHAR(10)` column with
  `'abc'` and `'abc '`; `WHERE C = CAST(? AS NVARCHAR(10))`, a `UNIQUE`
  constraint, `GROUP BY`, `LIKE`.
- **Impact:** wrong lookup results and unexpected IntegrityErrors for data with
  trailing spaces (common in data imported from fixed-length IBM i files).
- **Recommended correction:** document as a Known Limitation for every string
  type; optionally an opt-in exact comparison (`col = ? AND LENGTH(col) =
  LENGTH(?)`) after measuring its index impact.
- **Required tests:** the probe; an IBM i test documenting the behaviour.

---

### F-06 A Decimal with more decimals than the field is refused instead of rounded

- **Severity:** Medium
- **Status:** Verified (probe) for the mechanism: `qtemp_later_flags`
  (`DECIMAL(5, 0)` insert of 1.5: `22001`, CWB 30126) and
  `qtemp_decimal_values` (`CAST(? AS DECIMAL(5, 2))` with 1.2345: `22001`).
  Not verified with a Django `save()`.
- **Files:** `operations.py` (no `adapt_decimalfield_value`; Django's base
  returns the value unchanged since 4.x).
- **Problem:** `Invoice(amount=Decimal("1.005")).save()` on a
  `DecimalField(max_digits=5, decimal_places=2)` raises `DataError` (the driver
  refuses the marker sized by the column). PostgreSQL, MySQL and Oracle round
  on assignment. Values computed in Python (price x rate) commonly have extra
  decimals. Not in Known-Limitations.
- **Recommended correction:** quantize in `adapt_decimalfield_value` to
  `decimal_places` (rounding rule to be decided and documented; PostgreSQL rounds
  half away from zero), or document the error. Keep the existing behaviour for
  lookups (exact comparison, DECISIONS 2026-10-20).
- **Required tests:** IBM i test saving and reading back such values; offline
  unit test of the adapter.

---

### F-07 No query timeout; lock waits and network stalls block requests

- **Severity:** Medium (operational)
- **Status:** Verified (code); driver support Hypothesis
- **Files:** `base.py` (`OPTION_NAMES` has only `login_timeout`),
  `drivers/pyodbc.py` (`timeout=` only for login).
- **Problem:** No per-statement timeout. A statement waiting for a row lock
  blocks for the record wait (60 s for tables Django creates) before SQL0913; a
  half-open TCP connection can block a worker until the OS gives up.
- **Recommended correction:** `OPTIONS["query_timeout"]` mapped to pyodbc's
  `Connection.timeout` (`SQL_ATTR_QUERY_TIMEOUT`); document TCP keepalive and
  the record wait (`CHGPF WAITRCD`).
- **Required tests:** probe `qtemp_query_timeout` (a slow statement in the
  probe's own job, e.g. `CALL QSYS2.QCMDEXC('DLYJOB DLY(5)')`, with a 1 s
  timeout) to confirm the driver honours it; offline option tests.

---

### F-08 Readers wait for uncommitted writes of other jobs under `*CS`

- **Severity:** Medium (operational, concurrency)
- **Status:** Hypothesis for plain writes; Verified (probe) for
  `select_for_update` locks (`lib_select_for_update`,
  `REASON_READERS_WAIT_FOR_ROW_LOCKS`)
- **Problem:** Db2 for i's default concurrent access resolution is "wait for
  outcome": a `SELECT` that reaches a row another job changed and has not
  committed waits up to the record wait, then fails with SQL0913. PostgreSQL
  readers never wait. Known-Limitations documents it only for
  `select_for_update()`. No grep hit for "currently committed" anywhere in the
  repository.
- **Impact:** long-running transactions (migrations, batch jobs, admin bulk
  actions) stall web requests that read the same rows.
- **Recommended correction:** document generally; evaluate `USE CURRENTLY
  COMMITTED` (concurrent access resolution through QAQQINI
  `SQL_CONCURRENT_ACCESS_RESOLUTION` per job, or a driver keyword) as an option.
- **Required tests:** needs two jobs on a journaled table: a `lib_` probe with
  approval, or a dedicated IBM i.

---

### F-09 `driver_attributes` can override keywords the backend depends on

- **Severity:** Medium
- **Status:** Verified (code)
- **Files:** `drivers/pyodbc.py` `RESERVED_KEYWORDS` (DRIVER, DSN, SYSTEM, UID,
  PWD, DBQ, SSL, CMT, UNICODESQL, CCSID) vs `CONNECTION_DEFAULTS` (NAM,
  TRUEAUTOCOMMIT, DFT, TFT, XDYNAMIC, ...).
- **Problem:** `{"TRUEAUTOCOMMIT": "0"}` breaks the "failing autocommit statement
  leaves no partial changes" guarantee (Configuration.md line 188) that Django
  assumes; `{"NAM": "1"}` switches to system naming, where unqualified names
  resolve through the library list instead of `DBQ`, so queries can reach
  tables in other libraries. Other driver keywords (trace, translation, block
  fetch, lazy close) are not reviewed.
- **Recommended correction:** reserve `NAM`, `TRUEAUTOCOMMIT`, `DFT`, `TFT`
  (or switch to an allow-list of reviewed keywords such as `XDYNAMIC`,
  `DFTPKGLIB`, `PKG`).
- **Required tests:** offline tests of `connection_string()` refusals.

---

### F-10 More than 32,767 parameter markers fail with SQL0901; `max_query_params` is not set

- **Severity:** Medium
- **Status:** Verified (probe) for multi-row INSERT (`qtemp_bulk`,
  IBMI_NOTES line 1950: limit between 32,640 and 32,768); Hypothesis for
  `IN` lists.
- **Files:** `features.py` (no `max_query_params`), `operations.bulk_batch_size`
  (covers `bulk_create`, `bulk_update`, `in_bulk` and the delete collector).
- **Problem:** `filter(pk__in=<40,000 ids>)` and `prefetch_related()` over
  more than 32,767 parents build one statement with too many markers. SQL0901
  has SQLSTATE `58004` and maps to `InternalError`: an unclear error for a
  common pattern.
- **Recommended correction:** set `max_query_params = 32767`; consider refusing
  oversized `IN` lists with a clear `NotSupportedError`, and document the limit.
- **Required tests:** probe `qtemp_in_list_limit` (read-only, `SYSDUMMY1`); IBM i
  test with a large `__in` list.

---

### F-11 Dropping a table or column also drops dependent non-Django objects

- **Severity:** Medium (documented; design choice)
- **Status:** Verified (probe): `lib_drop`, `qtemp_column_copy`;
  Known-Limitations "Dropping a table also drops what depends on it",
  "Removing a field drops what depends on its column".
- **Files:** `schema.py` (`sql_delete_column` without `RESTRICT`; Django's
  `sql_delete_table` ... `CASCADE`, which is also Db2 for i's default).
- **Problem:** on a shared IBM i, views and foreign keys of other applications
  over a Django table vanish silently when a migration deletes a model or field;
  the referencing tables silently lose their constraints.
- **Recommended correction:** an option (or default) to use `RESTRICT`, or a
  pre-check that lists dependent objects not created by Django (`SYSVIEWDEP`,
  `SYSREFCST`) and refuses with their names. `column_copy` already uses
  `DROP COLUMN ... RESTRICT`, so the pattern exists.
- **Required tests:** offline DDL goldens; an IBM i test with a view on a table
  dropped by a migration.

---

### F-12 Widened columns break inserts on other long-lived connections

- **Severity:** Medium (documented)
- **Status:** Verified (probe) on one connection (`qtemp_final_table_after_alter`);
  the cross-connection case is an Unverified claim (Known-Limitations "A column
  that grew while a connection stays open" says so itself).
- **Files:** `drivers/pyodbc.py` (`with_current_parameter_types`, counts schema
  changes on the same connection only).
- **Problem:** after a deployment migration widens a column, workers with
  `CONN_MAX_AGE` keep the old parameter types of their `FINAL TABLE` inserts
  and refuse values that need the new size.
- **Recommended correction:** verify with two jobs (`lib_` probe or dedicated
  IBM i); if confirmed, consider making the statement text depend on something
  that changes with the table (cost to be measured), or recommend
  `CONN_MAX_AGE = 0` around deployments.
- **Required tests:** two-connection IBM i test (dedicated IBM i preferred).

---

### F-13 Test coverage measures a non-default configuration and omits contract-heavy Django modules

- **Severity:** Medium (test gap)
- **Status:** Verified (code and docs)
- **Files:** `tests/django_settings/settings_django_suite.py` and
  `settings_ibmi.py` (`"column_rename": "copy"`), `docs/status.toml` modules,
  `features.DatabaseFeatures.__init__` (removes the column-rename expected
  failures under `copy`).
- **Problem:**
  1. The status run and the IBM i tests run with `column_rename="copy"`, an
     opt-in. The default `refuse` path (27 expected failures, 3 skips) is not
     exercised on IBM i, and the copy path (data rewrite under `WITH NC`) is
     what the counts certify.
  2. Not measured on IBM i: `backends` (cursor, `last_executed_query`,
     unicode, threading, `CONN_MAX_AGE`), `transaction_hooks` (`on_commit`,
     which the backend itself uses for identity restarts), `fixtures` and
     `fixtures_regress` (identity restarts after `loaddata`), `serializers`,
     `model_fields` except JSONField (measured once: 2 failures with known
     causes, `docs/phases/phase-6.md`), `model_inheritance`, `custom_pk`,
     `many_to_one`, `one_to_one`, `generic_relations`, `raw_query`,
     `field_defaults` (`db_default`), `composite_pk`, `null_queries`,
     `aggregation_regress`, `cache` (database cache, uses `LIMIT ... OFFSET %s`),
     `sessions_tests`, `auth_tests`.
  3. No IBM i test for `Now()`, decimal assignment, trailing blanks, connection
     loss, `CONN_MAX_AGE` reuse or health checks.
- **Recommended correction:** add a status-run variant (or the IBM i tests)
  with default `OPTIONS`; measure the modules above one at a time (single
  modules are allowed on PUB400) and add them to `docs/status.toml`; mark
  connection-loss tests "requires a dedicated IBM i".

---

### F-14 `BinaryField` values over 1 MiB fail; the docs say bytes are not limited

- **Severity:** Low (documentation) to Medium (runtime error)
- **Status:** Hypothesis (Db2 for i: `BLOB` without a length is `BLOB(1M)`;
  the backend's `NCLOB` is documented the same way in `drivers/pyodbc.py`)
- **Files:** `base.py` (`"BinaryField": "BLOB"`), Known-Limitations "Strings
  longer than 1M characters are refused" ("Not limited: bytes ... Above 4 MiB
  they are sent in chunks").
- **Problem:** the column holds 1 MiB, so larger values fail with `22001`; the
  chunked path above 4 MiB is therefore unreachable for Django's own columns
  and unverified.
- **Required tests:** probe `qtemp_blob_default_length` (QTEMP table with
  `BLOB`, `SYSCOLUMNS.LENGTH`, insert 2 MiB).

---

### F-15 Full-width `％` and `＿` may act as LIKE wildcards on `NVARCHAR`

- **Severity:** Low
- **Status:** Hypothesis (Db2 LIKE on graphic/Unicode strings treats the
  full-width percent and underscore as wildcards; Django escapes only the ASCII
  ones)
- **Files:** `base.py` (`pattern_esc`, `operators`), Django's
  `prep_for_like_query`.
- **Impact:** `contains="５０％"` in Japanese or Chinese text matches more than
  intended.
- **Required tests:** probe `qtemp_like_fullwidth` (read-only, `SYSDUMMY1`).

---

### F-16 A duplicate key in one MERGE may raise `DataError`, not `IntegrityError`

- **Severity:** Low
- **Status:** Hypothesis
- **Files:** `compiler.py` `_merge_sql` docstring ("SQL0803 / SQL0788"),
  `drivers/base.py` (`"21": DataError`), Known-Limitations ("the same key twice
  in one call raises `IntegrityError`").
- **Problem:** SQL0788 (a target row matched twice) has SQLSTATE `21506`, which
  maps to `DataError`. Code catching `IntegrityError` around
  `bulk_create(update_conflicts=True)` misses it.
- **Required tests:** extend `qtemp_merge` with two source rows matching one
  existing target row; offline mapping test.

---

### F-17 `pyodbc.pooling = False` is set per connect, process-wide

- **Severity:** Low
- **Status:** Hypothesis
- **Files:** `drivers/pyodbc.py` (`Driver.connect`).
- **Problem:** pooling must be set before the first pyodbc connection of the
  process; if another library connected first with pooling on, closed backend
  connections may return to the ODBC pool and keep their job state (a `LOCK
  TABLE` lock held across `COMMIT HOLD`, the QAQQINI copy, a changed
  `INQMSGRPY`). It also changes pooling for other pyodbc users in the process.
- **Recommended correction:** detect an earlier pyodbc connection and warn or
  refuse; document.

---

### F-18 Stale and misplaced comments in `features.py`

- **Severity:** Low (maintainability; the lists are the measure of progress)
- **Status:** Verified (code)
- **Details:**
  - Comment "sql.rfind("headline") on the CREATE INDEX of a partial index ..."
    sits above `REASON_MERGE_RETURNS_NO_ROWS` and belongs to no entry.
  - Comment "assertIn("RETURNING ...", sql) ..." sits above
    `REASON_READERS_WAIT_FOR_ROW_LOCKS` and belongs to
    `REASON_FINAL_TABLE_NOT_RETURNING`.
  - The `can_rename_index` comment says "Combined alters stay off" while
    `supports_combined_alters = True` a few lines earlier.
  - The `test_db_allows_multiple_connections` comment says "basic and
    transactions use one or two" (outdated module list).

---

### F-19 `sequence_reset_sql()` has a side effect inside `atomic()`

- **Severity:** Low
- **Status:** Verified (code)
- **Files:** `operations.py` (`sequence_reset_sql`, `_after_transaction`).
- **Problem:** inside an atomic block it returns `[]` and schedules the
  `ALTER TABLE ... RESTART WITH` on commit. Callers that only want the SQL
  (`sqlsequencereset` run from code inside a transaction) get no SQL and an
  unexpected DDL at commit. In `TestCase` it never runs (documented, xfail
  `REASON_IDENTITY_RESTART_DEFERRED`).
- **Recommended correction:** restrict the deferral to the `loaddata` path, or
  document it in Known-Limitations.

---

### F-20 `dbshell` and `callproc()` are not available, without a clear error

- **Severity:** Low
- **Status:** Verified (code)
- **Files:** `client.py` (`executable_name = None`), `drivers/pyodbc.py`
  (`Cursor` has no `callproc`).
- **Problem:** `manage.py dbshell` fails with Django's generic
  `NotImplementedError`; `cursor.callproc()` raises `AttributeError` through
  `FormatStyleCursor.__getattr__`. Neither is in Known-Limitations' "Not
  available" list.

---

### F-21 Legacy columns with CCSID 65535 and mixed-case names

- **Severity:** Low
- **Status:** Hypothesis
- **Files:** `introspection.py` (`data_types_reverse`, `identifier_converter`
  lowercases every name), `operations.quote_name` (uppercases every name).
- **Problem:** `CHAR ... FOR BIT DATA` / CCSID 65535 columns come back as
  `bytes` but `inspectdb` writes `CharField`; a delimited mixed-case table
  created outside Django (`"Customer"`) is introspected as `customer` and then
  addressed as `"CUSTOMER"`, a different object.
- **Required tests:** probe `qtemp_ccsid_65535`; an `inspectdb` IBM i test.

---

### F-22 CI quality and supply chain

- **Severity:** Low
- **Status:** Verified (workflows, noxfile)
- **Details:** actions are pinned by major tag (`actions/checkout@v7`), not by
  commit SHA, including in the `pull_request_target` workflow that holds
  `statuses: write`; no coverage measurement; no static type checking (the code
  is annotated but unchecked); no dependency vulnerability audit
  (`pip-audit` / `uv` audit) beyond Dependabot; the `wheel` nox session is not
  run in CI, so packaging is not validated on every push.

---

### F-23 Global changes to Django at import time

- **Severity:** Low (forward compatibility with Django 6.2)
- **Status:** Verified (code)
- **Files:** `apps.py` (extends `django.db.models.options.DEFAULT_NAMES` and
  `migrations.state.DEFAULT_NAMES`), `compat.install_duration_adapter`
  (replaces `DurationField.get_db_prep_value` before 6.1; delegates for other
  vendors), `expressions.py` (`as_db2_for_i` on Django classes; vendor-scoped,
  delegates to `as_sql`).
- **Note:** all are scoped or idempotent; listed so the Django 6.2 review checks
  them first.

---

### F-24 Commit outcome after a lost connection is not documented

- **Severity:** Low
- **Status:** Verified (docs)
- **Problem:** an `08S01` during `COMMIT` leaves the outcome unknown. The backend
  correctly never retries, but the user docs (Troubleshooting covers `08S01`
  only for test runs) do not tell application authors that such a commit may
  have succeeded.

## 5. Audit of skips and expected failures

Classification of every reason in `features.py` (counts as in the code at
`c6c60d7`; per-version adjustments through `compat.py`).

| Reason | Kind | Tests | Classification | Comment |
|---|---|---|---|---|
| `REASON_NO_COLUMN_RENAME` | skip + xfail | 3 + 27 | Genuine unsupported (default `refuse`) | Removed at runtime with `column_rename="copy"`, which the status run uses (F-13). |
| `REASON_NO_SUCH_FUNCTION` | skip | 8 | Genuine unsupported | `REVERSE`, `HASH_SHA224/384` do not exist on 7.5; backend raises `NotSupportedError`. |
| `REASON_TRUNC_NULL_ZONEINFO` | skip | 1 (5.2, 6.0) | Django version incompatibility | Goes with 6.0. |
| `REASON_TIME_FRACTIONS` | xfail | 4 | Genuine unsupported | `TIME` has no fractions. |
| `REASON_TIME_ZONE_CONVERSION` | xfail | 7 | Known implementation gap | No tz database on Db2 for i; planned for phase 8. |
| `REASON_EXTRACT_IN_SQL` | xfail | 6 | Test checks another backend's SQL text | Not applicable. |
| `REASON_TRUNC_KIND_REFUSED` | xfail | 2 | Test expectation differs; backend is stricter | Not applicable (safe). |
| `REASON_IDENTITY_RESTART_DEFERRED` | xfail | 1 | Genuine restriction (SQL0910) plus a design choice | User-visible in `TestCase` with fixtures (documented). |
| `REASON_UNTYPED_NULL` | xfail | 1 | Known implementation defect | Planned fix (#82). |
| `REASON_TYPED_PARAMETER_MARKERS` | xfail | 1 | Test checks SQL text | Not applicable. |
| `REASON_UNTYPED_RAW_SQL_PARAMETER` | xfail | 3 | Genuine (user SQL) | Documented with a workaround. |
| `REASON_PENDING_ROW_CHANGES` | xfail | 7 | Genuine restriction, implementation could avoid it | Phase 7 marks it "analyse"; a commit between `UPDATE` and `ALTER` outside an outer `atomic()` might make them pass. |
| `REASON_ROWS_THEN_ALTER` | xfail | 1 | Genuine restriction | Test inserts then alters in one transaction. |
| `REASON_TYPE_NOT_IN_PLACE` | xfail | 10 | Genuine unsupported (no rebuild, by decision) | Documented with a migration recipe. |
| `REASON_CHECK_LIKE_COLUMN_PATTERN` | xfail | 2 | Genuine restriction plus environmental | PUB400 also refuses the name `CONSTRAINT` (SQL0601). |
| `REASON_MERGE_RETURNS_NO_ROWS` | xfail | 7 | Genuine restriction; implementation could re-select | Keys could be read back by `unique_fields` (cost, races). |
| `REASON_LOWERCASE_NAME_IN_SQL` | xfail | 1 | Test checks SQL text | Not applicable. |
| `REASON_NO_JSON_CHECK` | xfail | 1 | Genuine restriction | Probe `lib_json_check`. |
| `REASON_JSON_KEY_ORDER_AS_TEXT` | xfail | 1 | Genuine (as on Oracle, MariaDB) | Documented. |
| `REASON_JSON_IN_CHECK_OR_INDEX` | xfail | 3 | Genuine restriction | SQL0546, SQL0356. |
| `REASON_JSON_KEY_DOUBLE_QUOTE` | xfail | 2 | Genuine restriction | Probe `json_lookups`. |
| `REASON_READERS_WAIT_FOR_ROW_LOCKS` | xfail | 1 | Genuine semantic difference | See F-08 for the general case. |
| `REASON_JOIN_LOCKED_WITHOUT_FOR_UPDATE` | xfail | 7 | Test checks SQL text; semantics differ (wider locks) | Documented. |
| `REASON_FOR_UPDATE_TEXT` | xfail | 1 | Test checks SQL text | Not applicable. |
| `REASON_POSTGRESQL_LIKE_INDEXES` | xfail | 1 | Test specific to PostgreSQL | Not applicable. |
| `REASON_FINAL_TABLE_NOT_RETURNING` | xfail | 2 | Test checks SQL text | Not applicable. |

No entry was found that hides a defect without saying so. Candidates for
removal from the lists by implementation: `UNTYPED_NULL` (#82),
`PENDING_ROW_CHANGES` (analysis), `MERGE_RETURNS_NO_ROWS` (re-select),
`TIME_ZONE_CONVERSION` (phase 8). The 281 skips on 6.1 in TEST_STATUS are
mostly Django's own feature-flag skips (flags off with a reason in
`docs/features.toml`); they were not re-audited one by one here.

## 6. Test coverage gaps (summary)

| Area | Covered by | Gap |
|---|---|---|
| Time zones and `Now()` | `timezones` module, offline goldens | `Now()` against stored values (F-01). |
| Transactions | `transactions` module, `lib_*` probes | Other isolation levels (F-02); `transaction_hooks` not measured; commit after connection loss. |
| Connection lifecycle | 15 connection tests, `is_usable` unit tests | `CONN_MAX_AGE`, health checks, server-side job end, network loss (dedicated IBM i). |
| Concurrency | 7 two-connection row-lock tests | Reader/writer waits (F-08), `MERGE` races beyond the probe, parameter types across connections (F-12). |
| Data types | `basic`, `model_fields.test_jsonfield` | Rest of `model_fields`; decimal assignment (F-06); BLOB size (F-14); trailing blanks (F-05). |
| Fixtures and serialization | none on IBM i | `fixtures`, `serializers` (identity restarts after `loaddata`). |
| Contrib apps | none | `auth`, `sessions`, `contenttypes`, database cache. |
| Default configuration | offline tests | Django suite and IBM i tests run with `column_rename="copy"` (F-13). |
| Performance | none | No benchmarks: bulk insert batch sizes, catalog introspection, large result sets, LOB fetches. Benchmarks belong on a dedicated IBM i, never on PUB400. |

## 7. Operational risks (summary)

- Lock waits up to the record wait (60 s) for readers and writers (F-07, F-08).
- Long migrations hold exclusive locks until commit (`can_rollback_ddl`, `LOCK
  TABLE` before checks); web traffic on the same tables waits or fails. Not in
  the user docs as an operational note.
- Restart workers after migrations that widen columns (F-12, documented).
- Silent NULLs from data mapping errors (F-04).
- Tests reaching other libraries (F-03).
- RPG/CL level checks after record format changes are warned (W003).

## 8. Documentation inconsistencies

| Document | Statement | Issue |
|---|---|---|
| Known-Limitations, "Durations" | "In an update this **writes NULL**" | Not backed by a probe of `UPDATE` (F-04). |
| Known-Limitations, "Strings longer than 1M ..." | "Not limited: bytes (`BinaryField`, `BLOB`)" | The column is `BLOB(1M)` (F-14, hypothesis). |
| Known-Limitations, "inspectdb ..." | "Django's own `CharField` columns are `NVARCHAR` and not padded" | True for storage; comparisons still ignore trailing blanks (F-05). |
| Known-Limitations, "bulk_create() ..." | duplicates in one call raise `IntegrityError` | Possibly `DataError` for SQL0788 (F-16). |
| Configuration, `isolation_level` | lists `*NONE` as a valid value | No warning that transactions then do not work (F-02). |
| Configuration, `driver_attributes` | only the reserved keywords cannot be overridden | `TRUEAUTOCOMMIT` and `NAM`, both documented as required defaults, can be (F-09). |
| `features.py` comments | see F-18 | Stale or misplaced. |
| Known-Limitations, "Not available" | — | `dbshell`, `callproc()` missing (F-20). |

## 9. Distinguishing Db2 for i from Db2 LUW and Db2 for z/OS

All SQL the backend writes was checked for Db2 for i-specific forms; none of the
following LUW or z/OS-only forms is used: `ALTER TABLE ... RENAME COLUMN`
(refused, correctly), `TRUNCATE ... IMMEDIATE`, `NULLS FIRST/LAST`, `CREATE
INDEX ... INCLUDE` (off), `SET CURRENT LOCK TIMEOUT` (not available on IBM i,
which uses the record wait; relevant to F-07), `MERGE ... RETURNING`. Db2 for
i-specific forms in use are each backed by a probe: `FINAL TABLE ... ORDER BY
INPUT SEQUENCE`, `UNIQUE WHERE NOT NULL INDEX`, `WITH RS USE AND KEEP EXCLUSIVE
LOCKS`, `SAVEPOINT ... ON ROLLBACK RETAIN CURSORS`, `RENAME TABLE/INDEX`,
`FOR SYSTEM NAME`, `FOR COLUMN`, `QSYS2.OVERRIDE_QAQQINI`, `UX'...'` constants,
`WITH NC`. Claims that rest on IBM documentation only are marked Hypothesis
above.

## 10. Probes that would settle the hypotheses

All read-only or QTEMP-only (allowed on PUB400 without approval), one
connection, unless marked.

| Probe | Settles |
|---|---|
| `qtemp_current_timestamp_zone` | F-01 |
| `qtemp_cmt_none` | F-02 |
| `qtemp_update_mapping_errors` | F-04 |
| `qtemp_trailing_blanks` | F-05 |
| `qtemp_decimal_assignment` (a Django-shaped `INSERT` of 1.005 into `DECIMAL(5, 2)`) | F-06 |
| `qtemp_query_timeout` | F-07 |
| `qtemp_in_list_limit` | F-10 |
| `qtemp_blob_default_length` | F-14 |
| `qtemp_like_fullwidth` | F-15 |
| extend `qtemp_merge` (SQL0788 case) | F-16 |
| `qtemp_ccsid_65535` | F-21 |
| `lib_` probe (approval) or dedicated IBM i: two jobs, journaled table | F-08, F-12 |

## 11. Required tests for confirmed defects (before any fix)

Following the project rule "a regression test before the correction":

- F-01: IBM i test (`USE_TZ=True`, UTC) comparing a saved `Now()` with
  `timezone.now()`; offline golden of the new SQL.
- F-02: offline tests that `*NONE` is refused (or that the features follow it).
- F-03: offline test of `_create_test_db` refusing a model in another library.
- F-06: IBM i test saving `Decimal("1.005")` (expectation decided first).
- F-09, F-10, F-18, F-20: offline tests only.

## 12. Not checked in this phase

- Every feature-flag skip behind the 281 skipped Django tests on 6.1.
- `expressions.py` was reviewed for injection and delegation patterns, not line
  by line for each function's SQL (those are covered by goldens and the replay
  corpus).
- `column_copy.py` beyond its plan and safety checks.
- The `bin/` and `scripts/` tooling, except where it defines test behaviour.
- Performance: no measurement is possible without an IBM i, and none may run on
  PUB400.
