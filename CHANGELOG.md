# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `StringAgg`, as `LISTAGG` of an NCLOB with a typed separator: results up
  to 1M characters (longer fails with SQL0802), NULL over no values (the
  ODBC driver would return an empty string). See
  docs/user/Known-Limitations.md.
- Offline and pub400 guards that no comparison is emitted with untyped
  parameter markers on both sides (Db2 for i compares those wrongly,
  silently).
- `regex` and `iregex` lookups, as the `REGEXP_LIKE` predicate (ICU regular
  expressions, the database's dialect as on other backends; see
  docs/user/Known-Limitations.md). The pattern is sent as a typed
  `NVARCHAR(16370)` marker.

### Enabled features
- `supports_boolean_expr_in_select_clause`: predicates in the select list
  and GROUP BY are returned as BOOLEAN values.
- `supports_regex_backreferencing`.

### Fixed
- `Avg` of an integer field returned a truncated integer (Db2 for i's
  `AVG` of INTEGER is an INTEGER); the argument is now cast to DOUBLE when
  the result is a FloatField. `Avg` of a DecimalField stays DECIMAL.
- An aggregate whose `filter=` matches nothing (e.g. `Q(pk__in=[])`)
  failed with SQL0171 (`COUNT(NULL)`); the NULL is now typed, as
  `COUNT(CAST(NULL AS <argument type>))`.
- A selected `Q` or lookup annotation with a plain value
  (`annotate(b=Q(pages__lt=100))` on a full queryset) failed with SQL0418
  since `supports_boolean_expr_in_select_clause` was enabled: a select-list
  predicate with an untyped parameter marker is not valid. Such predicates
  are written as `CASE WHEN <predicate> THEN TRUE ELSE FALSE END` (still
  BOOLEAN). Grouping by such an annotation stays a known limitation.
- A predicate compared with another conditional expression
  (`filter(flag=Q(...))`, `annotate(b=LessThan(...)).filter(b=LessThan(...))`,
  `filter(has=Exists(...))` on an Exists annotation) failed with SQL0104:
  Db2 for i rejects a predicate as a comparison operand. Such operands are
  written as `CASE WHEN <predicate> THEN TRUE ELSE FALSE END`; boolean
  columns are not wrapped.
- `Exists()` conditions failed in the IBM i host server ("Error in host
  server data stream"): the subquery selected a parameter marker. It now
  selects a literal `1`.
- `Exists()` outside a WHERE condition (annotations, `Case(When(Exists()))`,
  `order_by()`, grouping) failed with SQL0104: Db2 for i accepts `EXISTS`
  only as a search condition. There it is rendered as
  `((SELECT 1 ... FETCH FIRST 1 ROWS ONLY) IS NOT NULL)`, which also stops
  at the first row; in WHERE it stays `EXISTS (...)`.
- Logged SQL (`connection.queries`, `CaptureQueriesContext`, the
  `django.db.backends` logger) shows the parameter values filled in
  (`last_executed_query()`), instead of `QUERY = ... - PARAMS = ...`. The
  text is for logging and debugging only; it is never executed.
- `Cast(..., CharField())` without `max_length`, and ordering by a `Value`
  with a `CharField` output (which Django wraps in such a cast), cast to
  `NVARCHAR(16370)`; they produced `CAST(... AS None)` (SQL0204).
- `SELECT DISTINCT` combined with `nulls_first` / `nulls_last` ordering
  failed with SQL0214. Db2 for i has no `NULLS FIRST/LAST`, and Django's
  emulation (`<expr> IS NOT NULL, <expr>`) must be in the select list for
  DISTINCT queries. The backend's compiler (`compiler.py`, now used for all
  queries) selects the predicate and the expression as hidden columns and
  orders by their positions; the hidden columns never appear in results.

## [0.1.0a2] - 2026-10-18

### Added
- A warning is logged at the first connection when the process locale is not
  UTF-8: the IBM i Access ODBC driver then garbles non-ASCII characters in
  result column names and error messages (data values are not affected).
- Release workflow (`.github/workflows/release.yml`) for signed `v*` tags:
  verifies the tag (annotated, OpenPGP-signed by the maintainer's key, on
  `main`, matching `__version__`, with a CHANGELOG section), builds sdist
  and wheel, runs the offline tier against the installed wheel and publishes
  a GitHub pre-release with both files. No PyPI.
- Probes for the string encoding investigation (`probe_encoding`,
  `probe_job_ccsid`, `probe_locale`); findings in `docs/IBMI_NOTES.md`.

### Changed
- Packaging: the version (`django_db2_for_i.__version__`) is the single
  source of the package version; classifier `Development Status :: 3 -
  Alpha`; project URLs. Alpha releases are published on GitHub only.

### Fixed
- Long strings arrive intact: string parameters of more than 8184 characters
  bound to `NCLOB`, `DBCLOB` or `CLOB` (such as a `TextField`) lost one
  character per 16369 bytes, silently. The cause was pyodbc sending long
  values in chunks of an odd byte size; the pyodbc driver now sets
  `maxwrite`, so values up to the maximum are sent in one piece. The limit
  for string parameters rises from 8184 to 1,048,576 UTF-16 units (the
  capacity of a `TextField` column); longer strings are refused with
  `NotSupportedError`. Bytes have no limit.
- Non-ASCII text in SQL statements is sent as Unicode: statement text and
  string parameters travel as UTF-8 (pyodbc `setencoding("utf-8",
  SQL_CHAR)`, driver keywords `UNICODESQL=1` and `CCSID=1208`, which can no
  longer be overridden). Before, the IBM i Access ODBC driver converted
  statement text to the job CCSID and silently replaced characters outside
  it (`€` in CCSID 273, emoji). `SchemaEditor.quote_value()` writes strings
  as plain `'...'` constants (column defaults keep `UX'...'`).

## [0.1.0a1] - 2026-10-17

Tagged as `v0.1.0a1` on commit `147e3fc`, without a release workflow. The
code under that tag still reports version `0.0.1.dev0`
(`django_db2_for_i.__version__`); the version number was set with 0.1.0a2.
The tag is not moved or recreated.

### Added
- Phase 0: project skeleton.
  - BSD-3-Clause license, contributing guide, README, changelog.
  - `pyproject.toml` (Django 6.1, pyodbc required) and the backend package
    layout as documented stubs.
  - Container environment: `docker/Dockerfile` with `offline` and `full`
    targets (IBM i Access ODBC Driver pinned by version and SHA256),
    `compose.yaml`, devcontainer, `.env.example`.
  - nox sessions `lint`, `offline` (Python 3.12–3.14 × Django 6.1), `pub400`,
    `probe`; pytest tier markers and an offline connection guard.
  - GitHub Actions workflow for the offline tier.
  - Read-only IBM i probes (`reachability`, `connect`, `sysinfo`, `libraries`).
  - Docs: `DECISIONS.md`, `DJANGO_VERSIONS.md`, `IBMI_NOTES.md` with the
    PUB400 findings, `TEST_STATUS.md`.
- Claude Code project settings deny access to `.env`.

- Phase 1: minimal backend for Db2 for IBM i 7.5 and Django 6.1.
  - `DatabaseWrapper` with a driver layer (`drivers/`: interface and pyodbc +
    IBM i Access ODBC Driver; SQL naming, commitment control `*CS`,
    TrueAutoCommit, extended dynamic SQL packages off) and server
    capabilities (`capabilities.py`: detection from the server version,
    profile `"7.5"`, per-capability overrides in `OPTIONS["capabilities"]`).
  - Conservative `DatabaseFeatures`: every optional flag off until Django's
    tests back it; fixed reason strings for skips and expected failures.
  - Type mapping (`NVARCHAR` for `CharField`, `BOOLEAN`, `TIMESTAMP(6)`, identity
    columns `GENERATED BY DEFAULT`), `CREATE`/`DROP TABLE`, literal defaults,
    minimal introspection.
  - Operations: pagination with `OFFSET` / `FETCH FIRST`, `last_insert_id`,
    `USE_TZ` conversion in the database's time zone, `TimeField` without
    microseconds, `sql_flush` with identity restarts outside the transaction,
    case-insensitive lookups, typed parameter markers for `Value`
    expressions, extracting date/time parts.
  - Test databases in an existing, journaled library (`TEST["CREATE_DB"] =
    False`), guarded by a marker table; never `CREATE`/`DROP SCHEMA`.
  - `OPTIONS["inquiry_message_reply"]` (opt-in): the IBM i job's inquiry
    message reply for the connection, restored to the original value at close,
    plus `connection.set_inquiry_message_reply()` /
    `restore_inquiry_message_reply()`. With `"*SYSRPYL"` and an administrator's
    `ADDRPYLE MSGID(CPA32B2) RPY('I')`, `DROP COLUMN` and narrowing column
    changes are allowed; without it such an `ALTER TABLE` raises an
    `OperationalError` that explains the cause and the fix.
  - Safety: passwords never appear in errors, logs, tracebacks or pytest
    reports; string parameters over 8184 UTF-16 units are refused (LOB
    parameters lose characters).
  - Tests: offline golden files for backend-specific SQL (55, all verified on
    IBM i 7.5), pub400 tier, `scripts/runtests.sh` for Django's own test
    suite (dotted labels, at most three per run) and
    `scripts/update_test_status.py`.
  - Probes for IBM i behaviour (journaling, commitment control, SQL features,
    string limits, column defaults, savepoints, extract functions, inquiry
    messages); findings in `docs/IBMI_NOTES.md`.
  - User documentation in `docs/user/`, mirrored to the GitHub wiki.

### Enabled features
- Savepoints (`uses_savepoints`, `can_release_savepoints`): nested `atomic()`
  blocks use `SAVEPOINT ... ON ROLLBACK RETAIN CURSORS`. Django's
  `transactions` tests: 85 passed, 3 skipped, no failures.

### Fixed
- Date and datetime lookups and `Extract()` (`__year`, `__month`, `__day`,
  `__week_day`, `__iso_week_day`, `__week`, `__quarter`, `__iso_year`,
  `__hour`, `__minute`, `__second`) are implemented. They run in the
  database's time zone; another current time zone raises `NotSupportedError`
  (see docs/user/Known-Limitations.md).
- Column defaults (`db_default`, and Python defaults when a migration adds a
  NOT NULL column) are written as bare literals with one rule per type;
  `CAST(...)` in a DEFAULT was rejected (SQL0574). Strings with quotes or
  non-ASCII characters use `UX'...'` constants, because Db2 for i stores
  escaped quotes in DEFAULT constants wrongly. Unsupported values raise
  `NotSupportedError`.

[Unreleased]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a2...HEAD
[0.1.0a2]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases/tag/v0.1.0a1
