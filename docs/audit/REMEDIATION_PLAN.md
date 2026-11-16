# Remediation plan: django-db2-for-i (Phase B, plan only)

> **Status of this document.** Written on 2026-11-16 by an independent Claude
> instance that had no context from earlier work on the project, offline only
> (no IBM i connection), on `main` at `c6c60d7`. It is a proposal: the maintainer has not approved it, and no item is scheduled until they do. It is kept here as
> written; later changes to the project are not reflected in it.

- **Based on:** `TECHNICAL_AUDIT.md` (Phase A, commit `c6c60d7`, 0.1.0b4).
- **Date:** 2026-11-16
- **Status:** proposal for the maintainer's approval. Nothing here has been
  implemented, committed or run. No IBM i or PUB400 connection was made.

## 0. Rules this plan follows

- Every item is **its own branch and pull request** (`<type>/<topic>` from
  `origin/main`), classified by `scripts/classify_pr.py`. The plan states the
  **expected** class; the script decides. Each PR gets the IBM i run its class
  asks for, on its latest commit, with the result posted before the label is
  removed.
- **Hypotheses are settled by a `qtemp_` probe before any backend change.**
  A probe's result goes into `docs/IBMI_NOTES.md` and, where a decision rests
  on it, `probes/results/` (`bin/probe --publish`).
- **`lib_` probes** (anything outside QTEMP, two jobs on a journaled table)
  only with the maintainer's approval **comment on GitHub**, passed to
  `bin/probe --approved <link>`. The plan proposes them; it does not assume
  approval.
- PUB400 limits: one PUB400 job at a time on this machine (`scripts/pub400.sh`),
  at most three connections and only for lock and concurrency tests, never the
  full Django suite, no benchmarks. Anything beyond that is marked
  **requires a dedicated IBM i** (phase 8).
- A regression test comes before the fix wherever the defect can be shown.
- User-visible changes update `docs/user/` in the same PR and add a changelog
  fragment (`changelog.d/<topic>.<type>.md`, renamed to the PR number).
  Feature-flag changes regenerate `docs/FEATURES.md` (`nox -s features`).
  Non-obvious choices go into `docs/DECISIONS.md`.

### Legend

| Column | Values |
|---|---|
| **Size** | S (under a day, under ~100 changed lines), M (a few days), L (a week or more, or several PRs) |
| **Class (expected)** | `full` = needs full IBM i run (core backend, `drivers/`, `base.py`, `creation.py`, `features.py`, ...); `targeted` = run-ibmi (other backend code, new SQL, IBM i tests); `docs` = docs/tests only |
| **User-visible** | **Yes** = behaviour, settings or limits users see: `docs/user/` + changelog fragment; **Docs** = documentation only; **No** = internal |
| **[M]** | A choice that is the maintainer's to make; the item waits for it |

## 1. Overview and order

Five waves. Wave 0 (probes) runs first because most High and Medium items
depend on its results. Waves 1 to 3 can then proceed in parallel branches,
merged one at a time; the one-PUB400-job rule serialises their IBM i runs.

| Wave | Items | Purpose | Needs a probe first |
|---|---|---|---|
| 0 | P-1 ... P-5 | Settle the hypotheses (read-only / QTEMP) | — |
| 1 | B-1, B-2, B-3 | Unsafe configurations and test isolation | No (B-1 uses P-2 only for its docs) |
| 2 | B-4 ... B-10 | SQL and value correctness | Yes, each its own probe |
| 3 | B-11 ... B-15 | Operational reliability | Partly; two need a `lib_` probe or a dedicated IBM i |
| 4 | B-16, B-17 | Test coverage | No |
| 5 | B-18 ... B-22 | Maintenance, docs, CI | No |

Priority within the plan (what to do first if time is short):
**P-1, B-1, B-2, B-3, B-4 (Now), B-5 (UPDATE NULL), B-6 (decimal), B-16 (default
configuration run)**. These are the items that stand between the current beta
and any production-readiness claim.

## 2. Wave 0: probes

All read-only or QTEMP-only, one connection, no approval needed. Each probe is
a new file `probes/qtemp_<topic>.py` with its own offline test entry
(`tests/offline/test_probes.py` checks names and the gate). Grouped into small
PRs by topic so each result is reviewed on its own.

| ID | Probe(s) | Settles | What it records | Size | Class (expected) |
|---|---|---|---|---|---|
| P-1 | `qtemp_current_timestamp_zone` | F-01 | `CURRENT TIMESTAMP`, `CURRENT TIMEZONE`, `CURRENT TIMESTAMP - CURRENT TIMEZONE` against the client's UTC clock; the job's `TIMZON` (`QSYS2.JOB_INFO` without parameters, to avoid SQL0443 poisoning) | S | docs |
| P-2 | `qtemp_cmt_none` | F-02 | With `CMT=0`: `INSERT`, `ROLLBACK`, count; `SAVEPOINT`, `ROLLBACK TO SAVEPOINT`; with `CMT=2` (`*CHG`) the same, for the record | S | docs |
| P-3 | `qtemp_update_mapping_errors` | F-04 | In a QTEMP table (`CMT=0`): `UPDATE` with timestamp overflow (`+ 30 DAYS` near 9999-12-31, `+ n MICROSECONDS` above 10^15), `CAST('abc' AS INTEGER)`, `/ 0`; the same through `INSERT ... SELECT`; on a nullable and a NOT NULL column; whether `RAISE_ERROR('22008', ...)` inside `CASE` is accepted on 7.5 | S | docs |
| P-4 | `qtemp_trailing_blanks`, `qtemp_like_fullwidth`, `qtemp_ccsid_65535` | F-05, F-15, F-21 | `NVARCHAR`/`VARCHAR`/`CHAR`: `=`, `IN`, `UNIQUE`, `GROUP BY`, `DISTINCT`, `LIKE` with `'abc'` vs `'abc '`; `LIKE` with full-width `％`/`＿` in pattern and data, and with `\％` escaped; a `CHAR FOR BIT DATA` column as pyodbc returns it and as `SYSCOLUMNS` describes it | M | docs |
| P-5 | `qtemp_decimal_assignment`, `qtemp_in_list_limit`, `qtemp_blob_default_length`, `qtemp_query_timeout`, extend `qtemp_merge` | F-06, F-10, F-14, F-07, F-16 | `INSERT` of 1.005 / 1.2345 into `DECIMAL(5, 2)` through an untyped and a typed marker; `VALUES 1 IN (?, ..., ?)` at 32,767 and 32,768 markers; `BLOB` default length in `SYSCOLUMNS` and a 2 MiB insert (and a `BLOB(10M)` with 5 MiB, the chunked path); pyodbc `Connection.timeout = 1` on `CALL QSYS2.QCMDEXC('DLYJOB DLY(5)')` (own job) and the error it gives; `MERGE` with two source rows matching one target row: SQLCODE and SQLSTATE | M | docs |

Proposed, needing approval or a dedicated IBM i (not in Wave 0):

| ID | Probe | Settles | Why it cannot be `qtemp_` | Proposal |
|---|---|---|---|---|
| P-6 | `lib_concurrent_reads` | F-08 | Two jobs must see the same journaled table | In one `.env` library, one table created and dropped by the probe (registered for `bin/ibmi-cleanup`), two connections: job A updates without commit, job B reads with the default and with `USE CURRENTLY COMMITTED` (statement clause and QAQQINI `SQL_CONCURRENT_ACCESS_RESOLUTION` through `OVERRIDE_QAQQINI`); record waits and errors. **Needs the maintainer's approval comment.** |
| P-7 | `lib_parameter_types_across_jobs` | F-12 | Job B widens a column job A inserts into | Same pattern as P-6: one table, two connections, `ALTER ... SET DATA TYPE` in job B, `FINAL TABLE` insert in job A before and after. **Needs the maintainer's approval comment**, or a dedicated IBM i. |

## 3. Wave 1: unsafe configurations and test isolation

### B-1 Refuse or follow the isolation level (F-02)

- **Change:** in `base.get_connection_params()`, refuse `*NONE` with
  `ImproperlyConfigured` naming the consequences. For `*CHG`, `*ALL`, `*RR`
  require an explicit acknowledgement (proposed:
  `OPTIONS["untested_isolation_level"] = True`) until a Django suite run exists
  for that level. **[M]** Alternative: accept `*NONE` and make
  `supports_transactions` / `uses_savepoints` / `can_release_savepoints` follow
  the level (Django then refuses `atomic()` with savepoints and warns), with a
  loud warning at connect. Recommendation: refuse; `*NONE` users on unjournaled
  libraries are better served by W001 and the journaling docs.
- **Tests:** offline (each level and alias; refusal message; the
  acknowledgement); IBM i: none needed for the refusal.
- **Probe first:** none for the code; P-2 for the docs' wording.
- **Dependencies:** none.
- **Size:** S. **Class:** `full` (`base.py`). **User-visible:** Yes
  (Configuration.md `isolation_level` row, Known-Limitations, changelog
  `changed`; a breaking change for anyone using `*NONE`, also in
  `docs/user/Upgrading.md`).

### B-2 Reserve the connection keywords the backend depends on (F-09)

- **Change:** add `NAM`, `TRUEAUTOCOMMIT`, `DFT`, `TFT` to
  `drivers/pyodbc.RESERVED_KEYWORDS`. **[M]** Alternative: an allow-list of
  reviewed keywords (`XDYNAMIC`, `DFTPKGLIB`, `PKG`, `BLOCKSIZE`, ...).
  Recommendation: extend the deny-list now (small, predictable), consider the
  allow-list for 1.0.
- **Tests:** offline (`connection_string()` refuses each, case-insensitive).
- **Probe first:** none.
- **Dependencies:** none.
- **Size:** S. **Class:** `full` (`drivers/`). **User-visible:** Yes
  (Configuration.md `driver_attributes`, changelog `changed`, Upgrading.md).

### B-3 Keep tests inside test libraries (F-03)

- **Change:** in `creation._create_test_db()`, collect the libraries named by
  the models under test (`split_table(db_table)`); refuse when any differs from
  `TEST["NAME"]`, unless it is mapped or allowed:
  - **[M] design choice:** (a) `TEST["LIBRARIES"] = {"SALES": "SALESTST"}`,
    applied while tests run (the mapped library must also pass the marker and
    journaling checks, and is cleaned up like `TEST["NAME"]`); or (b) only an
    explicit `TEST["ALLOW_OTHER_LIBRARIES"] = True` that keeps today's behaviour
    with a warning. Recommendation: (a), with (b) as the escape hatch.
  - Unmanaged models count too (they are the common case).
- **Tests:** offline (`plan_setup`-style pure function for the library check;
  refusal message; mapping applied to `quote_name`); IBM i: a model in the
  `other` library mapped to it (two connections at most; existing fixtures).
- **Probe first:** none.
- **Dependencies:** none; B-17 may reuse it.
- **Size:** M (L with mapping). **Class:** `full` (`creation.py`, and
  `operations.py` for the mapping). **User-visible:** Yes (Configuration.md
  "Test database", Known-Limitations "Tables in another library", changelog;
  breaking for projects that run tests with other-library models today).

## 4. Wave 2: SQL and value correctness

### B-4 `Now()` in the connection's time zone (F-01)

- **Change:** `Now.as_db2_for_i` in `expressions.py`: connection zone UTC →
  `CURRENT TIMESTAMP - CURRENT TIMEZONE`; otherwise **[M]**: (a) refuse with
  `NotSupportedError` unless the database `TIME_ZONE` is declared equal to the
  job's zone (new option, e.g. `OPTIONS["server_time_zone"] = "Europe/Brussels"`),
  or (b) always convert through UTC and then to the connection zone in Python
  only for selected values (cannot work inside `WHERE`). Recommendation: (a).
  With `USE_TZ = False` the same rule applies to `settings.TIME_ZONE`.
- **Tests:** offline goldens for `Now()` in select, filter and update; IBM i
  test with `USE_TZ = True`: save `Now()`, compare with `timezone.now()` within
  a minute; one with `USE_TZ = False` and `TIME_ZONE` equal to the job's zone.
- **Probe first:** P-1 (confirms the skew and that `CURRENT TIMEZONE`
  subtraction is exact, including microseconds and around a DST change if the
  system's zone has one).
- **Dependencies:** P-1.
- **Size:** M. **Class:** `full` (`expressions.py` is core). **User-visible:**
  Yes (`Now()` values change; Known-Limitations "Time zones", changelog
  `fixed`, DECISIONS entry).

### B-5 Silent NULLs from data mapping errors (F-04)

- **Change, depending on P-3:**
  - If `UPDATE`/`INSERT ... SELECT` raise an error: correct Known-Limitations
    "Durations" (docs only, `docs` class).
  - If they write NULL: guard duration arithmetic (`duration_expression_as_db2_for_i`)
    with `CASE WHEN <result outside 0001-01-01 .. 9999-12-31> THEN
    RAISE_ERROR('22008', '...') ELSE <result> END`, at least when the
    expression is an `UPDATE` value (**[M]**: everywhere, or only in
    `UPDATE`/`INSERT`; in a select list it changes today's documented NULL
    into an error). Document the remaining select-list behaviour more
    prominently (Troubleshooting, a top-level Known-Limitations entry).
- **Tests:** offline goldens of the guarded SQL; IBM i: `update(deadline=F("deadline")
  + timedelta(days=30))` near 9999-12-31 raises `DataError` and leaves the row
  unchanged (and the transaction usable).
- **Probe first:** P-3.
- **Dependencies:** P-3.
- **Size:** S (docs) or M (guard). **Class:** `docs` or `full`.
  **User-visible:** Yes.

### B-6 Decimal values with more decimals than the field (F-06)

- **Change, [M]:** (a) quantize in `operations.adapt_decimalfield_value()` to
  `decimal_places` with a documented rounding rule (PostgreSQL: half away from
  zero, `ROUND_HALF_UP`; Django's old `format_number`: the context's default,
  `ROUND_HALF_EVEN`), and refuse more integer digits than fit with a clear
  `DataError` before sending; or (b) keep the error and document it.
  Recommendation: (a) with `ROUND_HALF_UP`, matching PostgreSQL, Oracle and
  MySQL. Lookups keep their exact comparison (DECISIONS 2026-10-20): only
  saved values change.
- **Tests:** offline unit tests of the adapter (rounding, negative values,
  `max_digits` overflow, `None`, expressions untouched); IBM i: save and read
  back `Decimal("1.005")`, `Decimal("-1.005")`, `Decimal("123.456")` in a
  `DecimalField(5, 2)`; a filter with an over-precise value still compares
  exactly.
- **Probe first:** P-5 (`qtemp_decimal_assignment`).
- **Dependencies:** P-5.
- **Size:** S. **Class:** `full` (`operations.py`). **User-visible:** Yes
  (Known-Limitations, changelog `changed`).

### B-7 Trailing blanks in comparisons (F-05)

- **Change, depending on P-4:** document in Known-Limitations for every string
  type (not only `CHAR`): `exact`, `in`, `unique`, `distinct`, `GROUP BY`, and
  that `LIKE` differs. **[M]** Optionally an opt-in strict `exact`
  (`col = ? AND LENGTH(col) = LENGTH(?)`, which still uses the index for the
  first predicate) behind an option; not proposed for the default because it
  changes unique-key behaviour and plans.
- **Tests:** IBM i test that documents the behaviour (so a change on a later
  release is noticed); offline goldens if the opt-in is chosen.
- **Probe first:** P-4.
- **Dependencies:** P-4.
- **Size:** S (docs + test) or M (opt-in). **Class:** `targeted` (IBM i test)
  or `full` (opt-in). **User-visible:** Docs (or Yes with the opt-in).

### B-8 Parameter marker limit (F-10)

- **Change:** `DatabaseFeatures.max_query_params = 32767` (Django 6.1 uses it in
  `bulk_batch_size`; the backend's own `bulk_batch_size` stays); in
  `lookup_as_db2_for_i`, refuse an `In` lookup whose list alone exceeds the limit
  with `NotSupportedError` naming the limit, instead of SQL0901 from the server
  (**[M]**: refuse, or leave the server's error and only document).
- **Tests:** offline (feature value; refusal above the limit; goldens
  unchanged below); IBM i: an `__in` list just below the limit runs.
- **Probe first:** P-5 (`qtemp_in_list_limit`, to confirm the limit for `IN`
  and that SQL0901 leaves the connection usable).
- **Dependencies:** P-5.
- **Size:** S. **Class:** `full` (`features.py`, `expressions.py`).
  **User-visible:** Yes (Known-Limitations, changelog `limitation`/`changed`).

### B-9 `BinaryField` size and full-width LIKE wildcards (F-14, F-15)

- **Change, depending on P-4 and P-5:**
  - F-14: correct Known-Limitations ("Not limited: bytes"); **[M]** whether
    `BinaryField` becomes `BLOB(<larger>)` for new columns (a migration-visible
    type change for new tables only; existing columns keep `BLOB(1M)`).
    Recommendation: document now; size change only on user demand.
  - F-15: if confirmed, escape `％` and `＿` in the backend's LIKE preparation
    (`prep_for_like_query` override, and `pattern_esc` for the column forms).
- **Tests:** offline unit tests of the escaping and goldens; IBM i test with a
  full-width percent in `contains`.
- **Probe first:** P-4, P-5.
- **Dependencies:** P-4, P-5.
- **Size:** S each, two PRs. **Class:** `docs` (F-14) / `full` (F-15,
  `operations.py`, `base.py`). **User-visible:** Docs / Yes.

### B-10 Error class of a duplicate key in one MERGE (F-16)

- **Change, depending on P-5:** if SQL0788 arrives as `21506`, map SQLCODE
  `-788` to `IntegrityError` in `drivers/base._SQLCODE_ERRORS` (as for
  -530..-532), or correct the docs. **[M]** minor: which class users should
  catch (recommendation: `IntegrityError`, as the docs promise).
- **Tests:** offline mapping test; IBM i test with
  `bulk_create(update_conflicts=True)` and a duplicate key in one call.
- **Probe first:** P-5 (`qtemp_merge` extension).
- **Size:** S. **Class:** `full` (`drivers/`). **User-visible:** Yes (small).

## 5. Wave 3: operational reliability

### B-11 Query timeout option (F-07)

- **Change:** `OPTIONS["query_timeout"]` (seconds, default none) set on the
  pyodbc connection (`Connection.timeout`) in `drivers/pyodbc.py`, carried in
  `ConnectionParams`; the timeout error (`HYT00`) is already an
  `OperationalError`. Document the record wait (`CHGPF WAITRCD`) and TCP
  keepalive in Troubleshooting.
- **Tests:** offline (option validation, parameter passed); IBM i: a 1 s
  timeout on a 5 s `DLYJOB` in the test's own job raises `OperationalError`
  and the connection stays usable (or is marked unusable, as P-5 shows).
- **Probe first:** P-5 (`qtemp_query_timeout`).
- **Dependencies:** P-5.
- **Size:** S. **Class:** `full`. **User-visible:** Yes (new option,
  Configuration.md, changelog `added`).

### B-12 Readers waiting for writers (F-08)

- **Change:** first document the general case in Known-Limitations and
  Troubleshooting (docs PR, no probe needed beyond the existing row-lock
  evidence, worded as "expected; verified for `select_for_update()`").
  Then, depending on P-6: **[M]** an option
  `OPTIONS["concurrent_access_resolution"] = "currently_committed"` applied per
  job (QAQQINI override, as for CPA32B2, or a driver keyword if one exists).
- **Tests:** docs PR: none. Option: offline option tests; IBM i two-connection
  test (within the three-connection limit, lock and concurrency tests are
  allowed on PUB400).
- **Probe first:** P-6 (`lib_`, **maintainer's approval comment**).
- **Dependencies:** P-6 for the option.
- **Size:** S (docs) + M (option). **Class:** `docs` + `full`.
  **User-visible:** Docs, then Yes.

### B-13 Safer drops (F-11)

- **Change, [M]:** (a) a pre-check before `DROP TABLE` / `DROP COLUMN` that
  lists dependent views and foreign keys from other tables
  (`QSYS2.SYSVIEWDEP`, `SYSREFCST`) not created by the current migration
  state, and refuses with their names; or (b) an option
  `OPTIONS["drop_behavior"] = "restrict"` (default unchanged); or (c) make
  `RESTRICT` the default for 1.0 (breaking). Recommendation: (b) now,
  reconsider (c) for 1.0; `column_copy` already uses `RESTRICT`.
- **Tests:** offline DDL goldens for both behaviours (need verification
  stamps: `bin/verify`); IBM i: a view on a test table, `delete_model` refused
  under `restrict`, allowed by default.
- **Probe first:** none (`lib_drop`, `qtemp_column_copy` already show the
  behaviour); the catalog query for the pre-check (a) in a `qtemp_` probe.
- **Size:** M. **Class:** `full` (`schema.py`). **User-visible:** Yes.

### B-14 Parameter types across connections (F-12)

- **Change:** depending on P-7: if confirmed, keep the documentation and add
  operational guidance (restart workers, `CONN_MAX_AGE = 0` during deploys);
  **[M]** whether to add mitigation (e.g. catch the client-side `CWB0111`
  refusal on a `FINAL TABLE` insert, which happens before anything is sent,
  and retry once with a new statement text: safe only if P-7 shows the
  refusal is client-side every time; otherwise no retry, per the no-retry
  rule).
- **Tests:** two-connection IBM i test; **requires a dedicated IBM i** if the
  approval for P-7 is not given (it alters a table another job uses).
- **Probe first:** P-7.
- **Size:** S (docs) / M (mitigation). **Class:** `docs` / `full`.
  **User-visible:** Docs / Yes.

### B-15 Small operational gaps (F-17, F-24)

- **Change:** F-17: at connect, if pyodbc already has open connections from
  elsewhere and pooling was on, log a warning (or refuse, **[M]**); document
  that the backend switches pyodbc pooling off for the process.
  F-24: Troubleshooting entry "commit outcome unknown after `08S01`".
- **Tests:** offline (warning logic with a fake pyodbc module).
- **Probe first:** none.
- **Size:** S. **Class:** `full` (F-17, `drivers/`) and `docs` (F-24), two
  PRs. **User-visible:** Docs / small.

## 6. Wave 4: test coverage

### B-16 Measure the default configuration (F-13, part 1)

- **Change:** run the IBM i tests and the Django suite modules that touch
  schema changes (`schema`, `migrations`) also with default `OPTIONS`
  (`column_rename` not set), so the `refuse` path and its 27 expected failures
  and 3 skips are measured. **[M]** how: (a) a second settings module used in
  the status run for those two modules (adds two runs per Django version to
  the status run); or (b) switch the status run to defaults and keep `copy`
  in a separate run. Recommendation: (a). TEST_STATUS shows both rows.
- **Tests:** the runs themselves (PUB400, single modules, `--clean`).
- **Probe first:** none.
- **Dependencies:** none.
- **Size:** M. **Class:** `targeted` (settings, IBM i run tooling; per
  CONTRIBUTING, docs/tests that run on IBM i get `run-ibmi`).
  **User-visible:** No (TEST_STATUS only).

### B-17 More Django modules on IBM i (F-13, part 2)

- **Change:** measure one module per PR on 6.1, then 6.0 and 5.2; fix or list
  each failure with a fixed reason; add the module to `docs/status.toml`.
  Proposed order (backend contracts first): `backends`, `transaction_hooks`,
  `fixtures`, `fixtures_regress`, `serializers`, `model_fields` (whole module;
  two known failures to list), `field_defaults`, `custom_pk`,
  `model_inheritance`, `many_to_one`, `one_to_one`, `null_queries`,
  `raw_query`, `generic_relations`, `aggregation_regress`, `composite_pk`,
  `cache` (database cache), `sessions_tests`, `auth_tests` (labels).
  Tests in them that need more than three connections or a long run are
  skipped with the reason "requires a dedicated IBM i".
- **Tests:** the modules (PUB400, single modules, never more than three per
  invocation, `--parallel=1`); own IBM i tests for the common pattern of any
  flag that gets turned on.
- **Probe first:** as failures show.
- **Dependencies:** B-4, B-6 before `model_fields` and `timezones`-related
  modules, so their results are not measured twice.
- **Size:** L (many PRs, S-M each). **Class:** `targeted` per module (status
  list), `full` where a fix touches the core. **User-visible:** No, except
  fixes.

Connection-loss, `CONN_MAX_AGE` reuse under load, multi-process and
performance tests are **requires a dedicated IBM i** (phase 8); the plan adds
them to `docs/phases/phase-8.md` as items, not tests on PUB400.

## 7. Wave 5: maintenance, docs, CI

| ID | Findings | Change | Tests | Size | Class | User-visible |
|---|---|---|---|---|---|---|
| B-18 | F-18 | Fix the stale and misplaced comments in `features.py` (no code change). | none | S | `full` (`features.py` is core, though comment-only; the classification decides) | No |
| B-19 | F-19 | Document `sequence_reset_sql()`'s deferral inside `atomic()`; **[M]** optionally restrict the deferral to `loaddata`. | offline unit test if code changes | S | `docs` / `full` | Docs |
| B-20 | F-20, F-21 | Known-Limitations "Not available": `dbshell`, `callproc()`; a clear `NotSupportedError` for both (`client.py`, `FormatStyleCursor`); `inspectdb` notes for CCSID 65535 and mixed-case names (after P-4). | offline | S | `full` (`base.py`) / `targeted` (`client.py`) | Yes (small) |
| B-21 | F-22 | CI: pin actions by commit SHA (Dependabot keeps them current), run `nox -s wheel` in CI, add a dependency audit job (`uv`/`pip-audit` on the runtime dependencies), add coverage reporting to the offline sessions (report only, no threshold at first), consider a type checker on `django_db2_for_i/` (**[M]**: which one, and whether it gates). One PR each. | the CI itself | S each | per script (CI files; the gate's files are `full`) | No |
| B-22 | F-23 | Add a checklist item to the Django 6.2 review in `docs/DJANGO_VERSIONS.md`: `apps.py` DEFAULT_NAMES, `compat.install_duration_adapter`, the `as_db2_for_i` hooks. | none | S | `docs` | No |

## 8. Dependencies

```
P-1 ─► B-4 ─┐
P-2 ─► (B-1 docs)
P-3 ─► B-5  │
P-4 ─► B-7, B-9 (F-15), B-20 (F-21)
P-5 ─► B-6 ─┼─► B-17 (model_fields, timezones-related modules)
     ─► B-8, B-9 (F-14), B-10, B-11
P-6 (lib_, approval) ─► B-12 option
P-7 (lib_, approval or dedicated IBM i) ─► B-14
B-1, B-2, B-3, B-13, B-15, B-16, B-18 ... B-22: no dependencies
```

## 9. Decisions for the maintainer

| # | Item | Question | Recommendation |
|---|---|---|---|
| 1 | B-1 | Refuse `*NONE` (breaking), or follow it in the features with a warning? Opt-in for other untested levels? | Refuse; opt-in for `*CHG`, `*ALL`, `*RR`. |
| 2 | B-2 | Extend the deny-list, or switch to an allow-list? | Deny-list now; allow-list for 1.0. |
| 3 | B-3 | Library mapping under test, or only an explicit allow? | Mapping, plus the allow as escape hatch. |
| 4 | B-4 | What to do when the connection zone is neither UTC nor the job's zone? | Refuse unless `server_time_zone` is declared. |
| 5 | B-5 | If `UPDATE` writes NULL: guard everywhere or only in `UPDATE`/`INSERT`? | Only where a value is written; keep select-list NULLs documented. |
| 6 | B-6 | Round (which rule) or keep the error? | Round half up, like PostgreSQL. |
| 7 | B-7 | Docs only, or an opt-in strict `exact`? | Docs only for now. |
| 8 | B-8 | Refuse oversized `IN` lists in the backend, or document SQL0901? | Refuse with a clear message. |
| 9 | B-9 | Larger `BLOB` for new `BinaryField` columns? | Not now; document. |
| 10 | B-12 | Pursue `USE CURRENTLY COMMITTED` (and approve P-6)? | Yes, approve P-6; decide on the option after it. |
| 11 | B-13 | Pre-check, option, or `RESTRICT` by default? | Option now; reconsider the default for 1.0. |
| 12 | B-14 | Approve P-7, or leave it to a dedicated IBM i? Any retry? | Approve P-7 if the system allows it; no retry unless P-7 proves the refusal is always client-side. |
| 13 | B-15 | Warn or refuse when pyodbc pooling was already on? | Warn. |
| 14 | B-16 | Second settings run, or defaults in the status run? | A second run for `schema` and `migrations`. |
| 15 | B-17 | Which modules, in which order, and before or after 1.0? | The order above; at least `backends`, `transaction_hooks`, `fixtures`, `model_fields` before 1.0. |
| 16 | B-21 | Type checker and coverage: which tools, gating or not? | Report-only first. |
| 17 | P-6, P-7 | Approval comments for the two `lib_` probes. | — |

## 10. What requires a dedicated IBM i

- Connection loss and recovery tests (server-side job end, network drop,
  `08S01` during `COMMIT`).
- `CONN_MAX_AGE` and health checks under load; multi-process and
  multi-threaded runs with more than three connections.
- Benchmarks (bulk insert batch sizes, catalog introspection, large result
  sets, LOB fetches).
- F-12 across jobs if P-7 is not approved on PUB400.
- The full Django suite (phase 8).

## 11. How this leads to the production-readiness document

`PRODUCTION_READINESS.md` (later, after review) would list verifiable
criteria; from this plan: B-1 to B-6 merged with their IBM i runs; B-16 run
for every supported Django version; the B-17 modules named in decision 15 in
`docs/status.toml` with 0 failures; every High finding closed or documented
with evidence; P-1 to P-5 published; and the dedicated-IBM i items above either
run or listed as open risks.
