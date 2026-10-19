# Phase 1: Minimal backend

> Status: Done (2026-10-17)

The phase ended with the wrap-up PR [#16](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/16),
tagged as `v0.1.0a1`. The first part of the phase went straight to `main`
before the pull request workflow existed; those changes are linked by commit.
A follow-up encoding track ([#17](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/17)–[#21](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/21))
fixed the open findings from phase 1 and was released as `v0.1.0a2`; it is
recorded here because it closed phase 1's open tracks.

## Goal
Connection, cursor wrapper, driver layer, capabilities (detection + profiles),
basic type mapping, `CREATE`/`DROP TABLE`, transactions, test DB creation
including the "use existing schema" mode.

Done when: Django modules `basic` and `transactions` run on 6.1 against
PUB400, the offline tier has first golden files, and `TEST_STATUS.md` is
generated.

## What was done

### Driver, capabilities, wrapper
- Driver interface and pyodbc driver (SQL naming, `*CS`, TrueAutoCommit),
  extended dynamic SQL packages off, driver registry, optional default schema,
  rows as tuples ([`5260770`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/5260770),
  [`43542d8`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/43542d8),
  [`3da4626`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/3da4626)).
- `ServerCapabilities` with the `"7.5"` profile, detection from the server
  version and a warning for releases without a profile
  ([`3071ed8`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/3071ed8),
  [`8875f31`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/8875f31),
  [`b8e3784`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/b8e3784)).
- `DatabaseWrapper` and conservative `DatabaseFeatures`
  ([`42f9566`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/42f9566)).
- The password never appears in tracebacks or pytest reports
  ([`bb06838`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/bb06838),
  [`13aa605`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/13aa605)).

### Operations and schema
- `last_insert_id`, `OFFSET` / `FETCH FIRST` pagination, `USE_TZ` conversion,
  `sql_flush`, `TimeField` without microseconds, identity reset at
  `MAX(pk) + 1`, identity restarts outside the transaction (SQL0910)
  ([`880882f`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/880882f),
  [`4e16421`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/4e16421),
  [`16c63e3`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/16c63e3),
  [`dc4d155`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/dc4d155)).
- Literal defaults and minimal introspection; system catalog views left out
  of the table list ([`51e1c46`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/51e1c46),
  [`16160f6`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/16160f6)).
- Typed parameter markers for `Value` expressions and their cast rules
  ([#7](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/7),
  [#8](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/8)).
- Column defaults as bare literals, one rule per type, `UX'...'` for quotes
  and non-ASCII ([#12](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/12)).
- Date/time extraction and date lookups in the database time zone
  ([#14](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/14)).
- Opt-in `OPTIONS["inquiry_message_reply"]` for `ALTER TABLE` cancelled by
  CPA32B2 ([#15](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/15)).

### Transactions and test databases
- Test databases in an existing, journaled library, guarded by a marker table
  ([#3](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/3)).
- Savepoints enabled (`uses_savepoints`, `can_release_savepoints`), the first
  feature flag turned on ([#13](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/13)).

### Tests and tooling
- Offline wrapper tests and the pub400 connection smoke check
  ([`7248245`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/7248245)).
- 55 golden files for backend-specific SQL, all verified on IBM i 7.5
  ([#6](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/6)).
- `scripts/runtests.sh`, `scripts/update_test_status.py`, dotted labels
  ([#10](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/10),
  [#11](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/11)).
- String parameters over 8184 UTF-16 units refused (LOB data loss)
  ([#9](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/9));
  replaced by the encoding track below.

### Probes, docs, process
- Journal setup script and the probes (session, commitment, autocommit,
  operations, sequence, drop, features)
  ([`482b04d`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/482b04d),
  [`f5139e9`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/f5139e9),
  [`9e3800f`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/9e3800f),
  [`479ce9d`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/479ce9d),
  [`65ca558`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/65ca558)).
- User documentation in `docs/user/`, mirrored to the wiki
  ([`6af6cf6`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/6af6cf6),
  [`dd91617`](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/commit/dd91617));
  cascading `DROP TABLE` documented ([#4](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/4)).
- Git workflow, CI once per PR update, merge commits and signed commits on
  `main` ([#1](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/1),
  [#2](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/2),
  [#5](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/5)).
- Wrap-up: generated `TEST_STATUS.md`, changelog, the rule to run the full
  pub400 tier before a backend PR ([#16](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/16)).

### Encoding track (released as 0.1.0a2)
- Investigation of three encoding findings (A: non-ASCII statement text,
  B: escaped quote in a DEFAULT, C: LOB parameters losing characters)
  ([#17](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/17)).
- C fixed: pyodbc `maxwrite`, string parameters up to 1,048,576 UTF-16 units
  ([#18](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/18)).
- A fixed: statement text and string parameters as UTF-8
  (`setencoding`, `UNICODESQL=1`, `CCSID=1208`) ([#19](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/19)).
- Warning at connect when the process locale is not UTF-8
  ([#20](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/20)).
- Release 0.1.0a2 with a workflow for signed tags
  ([#21](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/21)).

## Key decisions
- `CharField` maps to `NVARCHAR` (CCSID 1200) ([DECISIONS](../DECISIONS.md#2026-10-17-charfield-maps-to-nvarchar-ccsid-1200)).
- `TrueAutoCommit=1`, so autocommit statements are atomic ([DECISIONS](../DECISIONS.md#2026-10-17-trueautocommit1-is-the-driver-default)).
- Extended dynamic SQL packages off (`XDYNAMIC=0`) ([DECISIONS](../DECISIONS.md#2026-10-17-extended-dynamic-sql-packages-off-xdynamic0)).
- Capabilities from the server version, named profiles and per-capability
  overrides ([DECISIONS](../DECISIONS.md#2026-10-17-capability-detection-and-profiles)).
- `BOOLEAN` is required for now ([DECISIONS](../DECISIONS.md#2026-10-17-boolean-is-required-for-now)).
- `sql_flush` uses `TRUNCATE`, `DELETE` for referenced tables ([DECISIONS](../DECISIONS.md#2026-10-17-sql_flush-uses-truncate-delete-for-referenced-tables)).
- `last_insert_id` via `IDENTITY_VAL_LOCAL()` ([DECISIONS](../DECISIONS.md#2026-10-17-last_insert_id-via-identity_val_local)).
- `TimeField` is native `TIME`, microseconds truncated ([DECISIONS](../DECISIONS.md#2026-10-17-timefield-is-native-time-microseconds-truncated)).
- Keep identity columns; defer identity restarts after commit ([DECISIONS](../DECISIONS.md#2026-10-17-keep-identity-columns-defer-identity-restarts-after-commit)).
- Fixed reason strings for skips and expected failures ([DECISIONS](../DECISIONS.md#2026-10-17-fixed-reason-strings-for-skips-and-expected-failures)).
- Test databases in an existing library, guarded by a marker table ([DECISIONS](../DECISIONS.md#2026-10-17-test-databases-in-an-existing-library-guarded-by-a-marker-table)).
- Merge commits, signed commits on `main` ([DECISIONS](../DECISIONS.md#2026-10-17-merge-commits-instead-of-rebase-merging-signed-commits-on-main)).
- Golden file format with a verification record ([DECISIONS](../DECISIONS.md#2026-10-17-golden-file-format-and-verification)).
- Typed parameter markers for `Value` expressions ([DECISIONS](../DECISIONS.md#2026-10-17-typed-parameter-markers-for-value-expressions)).
- Running Django's test suite on PUB400: at most three modules per run, two
  libraries ([DECISIONS](../DECISIONS.md#2026-10-17-running-djangos-test-suite-on-pub400)).
- Column defaults are bare literals, one rule per type ([DECISIONS](../DECISIONS.md#2026-10-17-column-defaults-are-bare-literals-one-rule-per-type)).
- Date functions run in the database time zone only ([DECISIONS](../DECISIONS.md#2026-10-17-date-functions-run-in-the-database-time-zone-only)).
- Inquiry message reply as an opt-in connection setting ([DECISIONS](../DECISIONS.md#2026-10-17-inquiry-message-reply-as-an-opt-in-connection-setting-cpa32b2)).
- Encoding track: `maxwrite` with a 1M-unit limit ([DECISIONS](../DECISIONS.md#2026-10-17-pyodbc-maxwrite-string-parameters-up-to-1m-utf-16-units)),
  statement text as UTF-8 ([DECISIONS](../DECISIONS.md#2026-10-17-statement-text-and-string-parameters-as-utf-8)),
  releases from OpenPGP-signed tags ([DECISIONS](../DECISIONS.md#2026-10-18-releases-from-openpgp-signed-tags-github-pre-releases-only)).

## IBM i findings
- The `default` and `other` libraries got a `QSQJRN` journal (approved); new
  tables are journaled automatically ([default](../IBMI_NOTES.md#journal-setup-in-the-default-library-nox--s-setup_journal------execute),
  [other](../IBMI_NOTES.md#journal-setup-in-the-other-library-nox--s-setup_journal------library-other---execute)).
- `NVARCHAR(n)` counts UTF-16 units; the driver refuses too-long values with
  `22001` instead of truncating ([IBMI_NOTES](../IBMI_NOTES.md#session-behaviour-probe----session)).
- Real transactions need a journaled table (SQL7008 with SQLSTATE `HY000`)
  ([IBMI_NOTES](../IBMI_NOTES.md#commitment-control-on-an-unjournaled-table-unicode-columns-probe_write)).
- With `TRUEAUTOCOMMIT=0` autocommit statements are not atomic
  ([IBMI_NOTES](../IBMI_NOTES.md#statement-atomicity-in-autocommit-mode-probe_autocommit)).
- The driver created an SQL package in `QGPL` with `XDYNAMIC=1`; removed after
  checking ownership ([IBMI_NOTES](../IBMI_NOTES.md#extended-dynamic-sql-packages-probe----packages)).
- 7.5 has `BOOLEAN`, `LIMIT`/`OFFSET`, `OFFSET`/`FETCH` and JSON functions
  ([IBMI_NOTES](../IBMI_NOTES.md#sql-features-for-the-capability-profiles-probe----features)).
- `TIME` drops microseconds silently; `TRUNCATE` of a referenced table fails
  (SQ20356) ([IBMI_NOTES](../IBMI_NOTES.md#operations-behaviour-probe_operations)).
- Identity restart fails with SQL0910 after row changes in the same
  transaction ([IBMI_NOTES](../IBMI_NOTES.md#identity-restart-inside-a-transaction-sql0910-pub400-tier)).
- `DROP TABLE` without an option behaves like `CASCADE`
  ([IBMI_NOTES](../IBMI_NOTES.md#drop-table-with-foreign-keys-and-views-probe_drop)).
- Db2 for i adds SQL catalog views to a library with its first constraint
  ([IBMI_NOTES](../IBMI_NOTES.md#sql-catalog-views-in-a-library-pub400-tier)).
- `CAST(...)` in a DEFAULT is rejected (SQL0574); an escaped quote is stored
  wrongly ([IBMI_NOTES](../IBMI_NOTES.md#column-default-constants-nox--s-probe_defaults)).
- `DROP COLUMN` and narrowing `ALTER` are cancelled by CPA32B2
  ([IBMI_NOTES](../IBMI_NOTES.md#alter-table-cancelled-by-cpa32b2-probe_inquiry-probe_job_reuse)).
- Savepoints need `ON ROLLBACK RETAIN CURSORS` ([IBMI_NOTES](../IBMI_NOTES.md#savepoints-nox--s-probe_savepoints------execute)).
- Scalar functions for date/time parts ([IBMI_NOTES](../IBMI_NOTES.md#extracting-datetime-parts-probe----extract)).
- Encoding track: root causes of A and C and why B is server-side
  ([IBMI_NOTES](../IBMI_NOTES.md#conclusions)); non-UTF-8 locale garbles
  column names and messages ([IBMI_NOTES](../IBMI_NOTES.md#non-utf-8-process-locale-nox--s-probe_locale)).

## Test status at the end of the phase
At the wrap-up ([#16](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/16), Django 6.1, PUB400, IBM i 7.5):

| Module | Tests | Passed | Skipped | Failures | Expected failures |
|---|---|---|---|---|---|
| basic | 83 | 80 | 3 | 0 | 0 |
| transactions | 88 | 85 | 3 | 0 | 0 |

- Offline tier: 55 golden files, all verified on IBM i 7.5.
- pub400 tier: 81 passed, 1 xfailed (`DROP COLUMN`: no CPA32B2 entry in the
  system reply list).
- After the encoding track ([#21](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/21)):
  pub400 tier 94 passed, 1 xfailed; 56 golden files, all verified.
- Current status: [TEST_STATUS.md](../TEST_STATUS.md).

## Carried forward
- Table-rebuild fallback for data-losing `ALTER TABLE` without a CPA32B2
  reply list entry: open question for phase 4 ([DECISIONS](../DECISIONS.md#2026-10-17-open-question-for-phase-4-table-rebuild-for-data-losing-alter-table)).
- Time zone conversion between zones (`timezones` tests): a later phase.
- Identity gap: measure again on the `fixtures` module.
- Finding B (escaped quote in DEFAULT): server-side, `UX'...'` constants stay.
- Column order of created tables: [#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23),
  opened after the wrap-up, for phase 4.
- Needs a dedicated IBM i: the full tier, Django 5.2 support (phase 3), the
  CPA32B2 reply list entry, `CREATE SCHEMA` test databases, multiple
  connections.

## Links
- Tag `v0.1.0a1` (commit `147e3fc`, merge of #16): [CHANGELOG 0.1.0a1](../../CHANGELOG.md#010a1---2026-10-17).
- Tag `v0.1.0a2`, the encoding track and release workflow: [CHANGELOG 0.1.0a2](../../CHANGELOG.md#010a2---2026-10-18),
  [GitHub release](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases/tag/v0.1.0a2).
- [docs/user/Known-Limitations.md](../user/Known-Limitations.md),
  [String encoding investigation](../IBMI_NOTES.md#string-encoding-investigation-nox--s-probe_encoding).
