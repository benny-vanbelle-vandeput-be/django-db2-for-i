# Phase 2: Queries & pagination

> Status: Done (2026-10-19)

## Goal
Make Django's query machinery work on Db2 for i, driven by the Django test
modules `queries`, `lookup`, `ordering`, `aggregation` and `expressions`
(CLAUDE.md, section 9), with the feature flags enabled one at a time, each with
its own pub400 test for the real-world pattern.

## What was done

**Compiler: Db2 for i's SQL rules**
- `SELECT DISTINCT` with emulated NULL ordering: hidden columns, ORDER BY by
  position. [#26](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/26)
- `Exists()` by context (EXISTS only as a search condition, a first-row
  subquery elsewhere); predicates in the select list, as comparison operands,
  and as select columns with untyped markers. [#31](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/31), [#32](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/32), [#33](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/33), [#34](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/34), [#35](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/35)
- GROUP BY expressions with parameter markers through a LATERAL grouping
  table. [#45](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/45)
- `NOT` of a BOOLEAN value as a CASE value; boolean values as conditions
  compared with `TRUE` / `FALSE` (Db2 for i's `NOT <value>` is TRUE for NULL);
  selected predicates three-valued (`None` for UNKNOWN). [#48](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/48), [#51](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/51), [#81](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/81), [#84](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/84)
- `IN (subquery)` outside a search condition as a three-valued BOOLEAN, for
  any number of columns; a self-referencing delete's WHERE as a condition.
  [#71](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/71), [#73](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/73), [#74](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/74)

**Values and parameters**
- Typed parameter markers: UUID, durations, foreign keys and IP addresses;
  string values longer than their column (never truncated); `iexact` without
  LIKE escaping; logged SQL with parameters filled in. [#30](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/30), [#50](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/50), [#63](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/63), [#65](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/65), [#66](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/66)
- `CharField` without `max_length` cast to `NVARCHAR(16370)`. [#25](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/25)

**Functions, aggregates, durations**
- `regex` / `iregex` with `REGEXP_LIKE`; date/time truncation; `%`, `^`,
  bitwise operators and shifts. [#29](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/29), [#44](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/44), [#47](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/47)
- `Avg` of an integer as `AVG` of a DOUBLE; a Case collapsed to a typed NULL;
  `StringAgg` as `LISTAGG` of an NCLOB, with ordering. [#36](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/36), [#37](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/37), [#38](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/38)
- `DurationField` (BIGINT microseconds), duration arithmetic, exact temporal
  subtraction, BIGINT range checks. [#56](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/56), [#57](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/57), [#59](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/59)

**Feature flags enabled**
- `supports_any_value`, `supports_subqueries_in_group_by`,
  `supports_select_union`, `supports_aggregate_order_by_clause`,
  `supports_temporal_subtraction`, `nulls_order_largest`,
  `supports_select_intersection` / `supports_select_difference`,
  `allow_sliced_subqueries_with_in`, `supports_tuple_lookups`,
  `supports_slicing_ordering_in_compound` / `supports_parentheses_in_compound`.
  [#39](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/39), [#40](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/40), [#42](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/42), [#43](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/43), [#59](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/59), [#68](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/68), [#72](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/72), [#77](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/77), [#78](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/78), [#80](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/80)

**Driver**
- A connection left unusable by SQL0443 on a QSYS2 service is marked unusable
  so Django reconnects. [#60](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/60)

**Test infrastructure and process**
- Changelog fragments; golden cases and pub400 tests split by area; golden
  stamps per verification level. [#41](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/41), [#58](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/58)
- README badges and the generated project status; the backend commit in
  TEST_STATUS; `queries` summed from its labels; clearer badges. [#49](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/49), [#52](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/52), [#62](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/62), [#64](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/64)
- `runtests.sh --debug-sql`; executed SQLite references for tuple lookups and
  boolean conditions (`tests/offline/reference_db.py`). [#79](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/79), [#78](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/78), [#81](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/81)
- Working rules: QTEMP exception for probes, the `needs-full-tier` label for
  backend PRs. [#83](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/83)

**Known limitations documented** (docs/user/Known-Limitations.md)
- Untyped parameters in `RawSQL` / `extra()`; conversion errors in selected
  values give NULL; numeric filter values that don't fit the column (issue
  [#69](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/69)). [#54](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/54), [#61](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/61), [#67](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/67), [#70](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/70)

## Key decisions
- DISTINCT with emulated NULL ordering: [DECISIONS](../DECISIONS.md#2026-10-18-distinct-with-emulated-null-ordering-hidden-columns-order-by-position)
- Exists() by context: [DECISIONS](../DECISIONS.md#2026-10-18-exists-by-context-predicates-in-the-select-list)
- Predicates as operands / select columns: [DECISIONS](../DECISIONS.md#2026-10-18-predicates-as-comparison-operands), [DECISIONS](../DECISIONS.md#2026-10-18-predicates-as-select-columns-case-when--then-true-else-false-end), [DECISIONS](../DECISIONS.md#2026-10-19-selected-predicates-are-three-valued-issue-75)
- Never compare two untyped markers: [DECISIONS](../DECISIONS.md#2026-10-18-never-compare-two-untyped-parameter-markers)
- Ordered compound queries wrapped in LATERAL: [DECISIONS](../DECISIONS.md#2026-10-18-ordered-union-queries-wrapped-in-select--from-lateral-)
- GROUP BY through a LATERAL grouping table: [DECISIONS](../DECISIONS.md#2026-10-18-group-by-expressions-with-values-through-a-lateral-grouping-table)
- NOT of a BOOLEAN value; boolean values as conditions: [DECISIONS](../DECISIONS.md#2026-10-19-not-of-a-boolean-value-as-a-case-value-everywhere), [DECISIONS](../DECISIONS.md#2026-10-19-boolean-values-as-conditions-are-compared-with-true--false)
- Durations and temporal subtraction: [DECISIONS](../DECISIONS.md#2026-10-19-temporal-subtraction-in-exact-microseconds)
- Unusable connections: [DECISIONS](../DECISIONS.md#2026-10-19-unusable-connections-detect-and-let-django-reconnect)
- Typed markers for long strings; long Values: [DECISIONS](../DECISIONS.md#2026-10-19-typed-markers-only-for-string-values-longer-than-the-column), [DECISIONS](../DECISIONS.md#2026-10-19-a-string-value-longer-than-its-field-gets-its-own-bucket)
- IN (subquery) rewrite: [DECISIONS](../DECISIONS.md#2026-10-19-in-subquery-outside-a-search-condition-as-a-three-valued-boolean), [DECISIONS](../DECISIONS.md#2026-10-19-one-in-subquery-rewrite-for-any-number-of-columns)
- Tuple lookups: [DECISIONS](../DECISIONS.md#2026-10-19-supports_tuple_lookups-with-expanded-in-lists-and-comparisons)
- Changelog fragments: [DECISIONS](../DECISIONS.md#2026-10-18-changelog-fragments-golden-cases-and-pub400-tests-split-by-area)

## IBM i findings
- Phase 2 SQL feature probe (compound queries, subqueries, predicates, GROUP BY): [IBMI_NOTES](../IBMI_NOTES.md#sql-features-for-phase-2-probe----queries)
- `NOT` of a NULL BOOLEAN value is TRUE; comparisons are three-valued: [IBMI_NOTES](../IBMI_NOTES.md#predicates-as-three-valued-values-probe----selected_predicates) (and the boolean part of [IBMI_NOTES](../IBMI_NOTES.md#sql-features-for-phase-2-probe----queries))
- IN (subquery) and `= ANY` are rejected inside CASE WHEN (SQL0115): [IBMI_NOTES](../IBMI_NOTES.md#in-subquery-inside-case-when-probe----in_subquery-probe----queries), [IBMI_NOTES](../IBMI_NOTES.md#tuple-in-subquery-probe----tuple_in)
- Row-value IN lists (SQL0104) and ordering comparisons (SQL0115) are rejected: [IBMI_NOTES](../IBMI_NOTES.md#row-value-predicates-for-tuple-lookups-probe----tuple_lookups)
- Ordered and sliced parts of compound queries work in every shape: [IBMI_NOTES](../IBMI_NOTES.md#ordered-and-sliced-parts-of-compound-queries-probe----compound_parts)
- Untyped markers are sized by the column (CWB0111, never truncated): [IBMI_NOTES](../IBMI_NOTES.md#string-parameters-longer-than-the-column-nox--s-probe----long_string_params)
- SQL0443 on a service can leave the connection unusable: [IBMI_NOTES](../IBMI_NOTES.md#statements-that-leave-the-connection-unusable-nox--s-probe----fetch_errors)
- Conversion errors in the select list give NULL without a warning: [IBMI_NOTES](../IBMI_NOTES.md#data-mapping-errors-in-the-select-list-nox--s-probe----mapping_errors)
- Durations, truncation, LISTAGG, extract, operators: [IBMI_NOTES](../IBMI_NOTES.md#durations-probe----durations), [IBMI_NOTES](../IBMI_NOTES.md#truncating-dates-and-times-probe----trunc), [IBMI_NOTES](../IBMI_NOTES.md#listagg-for-stringagg-probe----listagg), [IBMI_NOTES](../IBMI_NOTES.md#extracting-datetime-parts-probe----extract), [IBMI_NOTES](../IBMI_NOTES.md#operators-for-combine_expression-probe----queries-area-arith)

## Test status at the end of the phase
Release run for 0.1.0a3 on `main` at `8434482` (2026-10-19, 20:09–21:14 UTC; Django
6.1, Python 3.14, PUB400, one connection at a time), the first run under the release-run
policy; every module log records that commit ([TEST_STATUS](../TEST_STATUS.md)):

| Module | Tests | Passed | Skipped | Expected failures | Failed / errors |
|---|---|---|---|---|---|
| basic | 83 | 80 | 3 | 0 | 0 |
| transactions | 88 | 85 | 3 | 0 | 0 |
| ordering | 43 | 43 | 0 | 0 | 0 |
| lookup | 148 | 141 | 5 | 2 | 0 |
| aggregation | 168 | 152 | 16 | 0 | 0 |
| expressions | 213 | 206 | 5 | 2 | 0 |
| queries (10 labels) | 506 | 482 | 21 | 3 | 0 |
| **Total** | **1249** | **1189** | **53** | **7** | **0** |

- Own pub400 tier on the same commit: 238 passed, 1 expected failure
  (`test_drop_column_with_the_option`, no CPA32B2 entry in the system reply list);
  goldens: 150 verified on PUB400 (IBM i 7.5), 0 failed.
- Offline tier: lint and the offline tests for Python 3.12, 3.13 and 3.14 with Django
  6.1, as parallel CI jobs since [#87](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/87).

## Carried forward
- Numeric filter values out of range: issue [#69](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/69) (after phase 2, before phase 3).
- `annotations` / `expressions_case` errors outside the phase 2 modules: issue [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82).
- Comparison operands (`PredicateValue`) still give `FALSE` for UNKNOWN; a separate decision ([DECISIONS](../DECISIONS.md#2026-10-19-selected-predicates-are-three-valued-issue-75)).
- Column order of created tables: issue [#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23) (phase 4).
- Phase 3, Django 6.0 and 5.2 support: approved plan in [phase-3.md](phase-3.md); before it, issue
  [#69](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/69) and the offline query corpus for 6.1.

## Links
- Release: `v0.1.0a3` (2026-10-20); [CHANGELOG](../../CHANGELOG.md#010a3---2026-10-20).
- [TEST_STATUS](../TEST_STATUS.md), [Known limitations](../user/Known-Limitations.md).
