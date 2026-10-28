# Django versions

Reference: the Django versions this backend supports, the Python versions
tested with each, and the impact of each version's "Database backend API"
changes on this backend. The plan and the reasoning are in
[phases/phase-3.md](phases/phase-3.md) (phase 3, "Django 6.0 and 5.2 support").

Status of 2026-10-21 (phase 3 done): the backend supports Django 5.2, 6.0 and
6.1, each with the four test sets on every Python, the goldens verified on
PUB400 and a release run (see [phase-3.md](phases/phase-3.md)). Nothing in
this file marked "planned" is implemented yet.

## Supported versions and the drop rule

| Django | End of security support | Status in this backend |
|---|---|---|
| 6.1 | December 2027 | supported |
| 6.0 | April 2027 | supported (phase 3 step A) |
| 5.2 LTS | April 2028 | supported (phase 3 step B) |

- **Source** for the dates: djangoproject.com/download, the "Supported
  versions" table (column "End of extended support"), fetched 2026-10-19.
- **Drop rule** (CLAUDE.md section 3): a version stays supported until its
  security support ends. It is dropped in the first release of this backend
  after that date, 6.0 included. So 6.0 goes about a year before 5.2.
- **6.2 LTS** is added alongside the versions still supported when it ships.
- Django 4.2 is not supported.

## Python support and minimum patch releases

| Django | Django's Python support | Our matrix | pyproject floor |
|---|---|---|---|
| 6.1 | 3.12, 3.13, 3.14 | 3.12, 3.13, 3.14 | 6.1.0 |
| 6.0 | 3.12, 3.13, 3.14 | 3.12, 3.13, 3.14 | 6.0.3 (pyproject floor) |
| 5.2 LTS | 3.10–3.14 (3.14 from 5.2.8) | 3.12, 3.13, 3.14 | 5.2.12 (pyproject floor) |

**Why these floors**
([DECISIONS](DECISIONS.md#2026-10-19-minimum-django-patch-releases-5212-603-and-610)):
they are the patch releases with the latest Python 3.14 fixes, and the matrix
tests 3.14 on every version. The release notes say:

- **6.1**: `docs/releases/6.1.txt`, "Python compatibility": supports 3.12,
  3.13 and 3.14.
- **6.0**: `docs/releases/6.0.txt`: "Django 6.0 supports Python 3.12, 3.13, and
  3.14." The later 3.14 fixes are:
  - `6.0.1.txt`: "Fixed a bug where management command colorized help
    (introduced in Python 3.14) ignored the `--no-color` option and the
    `DJANGO_COLORS` setting";
  - `6.0.3.txt`: "Fixed `NameError` when inspecting functions making use of
    deferred annotations in Python 3.14".
- **5.2**:
  - `docs/releases/5.2.txt`: "Django 5.2 supports Python 3.10, 3.11, 3.12,
    3.13, and 3.14 (as of 5.2.8)."
  - `5.2.8.txt`: "It also adds compatibility with Python 3.14."
  - 3.14 fixes follow in 5.2.9, 5.2.10 ("one bug related to support for
    Python 3.14") and 5.2.12 ("one bug related to support for Python 3.14").

**Always use the latest security release** of a supported Django series. The
floors are minimums, not recommendations.

## Database backend API impact

Base: Django 6.1. Each item is from the "Database backend API" section of the
release notes, plus closely related "Models" items where they change the SQL
or the backend hooks. The analysis compared `stable/6.1.x` (`1e01021`),
`stable/6.0.x` (`52e5ba1`) and `stable/5.2.x` (`cae7247`) with the backend;
details are in the approved phase 3 plan (sections 2 and 3 of
[phase-3.md](phases/phase-3.md) at the merge of #86; the file is the phase
record now).

Status values:
- **done**: in the backend today;
- **checked**: no backend change needed, shown by the goldens and the test
  runs of that version;
- **n/a**: needs nothing;
- **planned (step A PR n / step B PR n)**: the PR numbers refer to the
  phase 3 step plan;
- **later (phase n)**: belongs to a later phase.

### Django 6.1 (base)

| Item | Backend | Status |
|---|---|---|
| `DatabaseOperations.adapt_durationfield_value()` added | Overridden: BIGINT range check ([#57](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/57)) | done |
| `DatabaseIntrospection.get_relations()` returns `(field, table, db_on_delete)` | Implemented; the tuple comes from `compat.relation()` (`(field, table)` on 6.0 and 5.2), `SYSREFCST.DELETE_RULE` mapped with Django's own `on_delete_types` (6.1; its keys are Db2's values) | done (phase 4) |
| `DatabaseFeatures.supports_inspectdb` | `True` (phase 4 step D); 6.0 and 5.2 have no such flag and always offer `inspectdb` | done (phase 4) |
| `prohibits_dollar_signs_in_column_aliases` removed | Never set | n/a |
| `binary_placeholder_sql(value, compiler)` returns `(sql, params)` | Not overridden; a bytes `Value` is refused | later (with binary values) |
| `get_geom_placeholder()` renamed | GIS, not supported | n/a |
| `DatabaseFeatures.supports_bit_aggregations` | `False` | done |
| Aliases quoted systematically (`SQLCompiler.quote_name()`) | The goldens are 6.1 SQL | done |
| Default model ordering applied to combined querysets | Compound query goldens are 6.1 SQL | done |
| DB-level `on_delete` (`supports_on_delete_db_*`) | `False` | later (phase 6, 6.1+) |

### Django 6.0: what it lacks compared with 6.1

All of these also apply to 5.2.

| Difference | Impact on the backend | Status |
|---|---|---|
| `adapt_durationfield_value()` is never called; `DurationField` converts itself | Values still arrive as microseconds, but the range check is skipped, so the driver would raise an unclear error. Kept through `compat.py` ([DECISIONS](DECISIONS.md#2026-10-19-the-duration-range-check-on-every-supported-django-version)), with a pub400 test per version. `compat.install_duration_adapter()` routes the values through it ([DECISIONS](DECISIONS.md#2026-10-20-the-duration-range-check-before-django-61)). | done (step A PR 3) |
| Aliases are not quoted (`quote_name_unless_alias()`) | Different SQL text, so 6.0 needs its own goldens. Unquoted aliases fold to uppercase like our quoted ones; the 154 6.0 goldens differ from 6.1's only in that quoting, and all 154 were accepted on PUB400 ([#110](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/110)). | done |
| Combined querysets ignore the default model ordering | Different SQL and results: goldens per series. The compound-query goldens of 6.0 and 5.2 equal 6.1's (apart from alias quoting), and the `queries` labels pass on all three versions. | checked |
| `mark_expected_failures_and_skips` has no `ImportError` fallback | A skip or expected-failure name that 6.0's suite lacks breaks every run, so the lists must be per Django version. All names in today's lists exist in the 6.0 and 5.2 suites. Two `schema` expected failures pass on 5.2 and are left out there (`compat.PASSING_ON_THIS_VERSION`, 2026-10-24). | checked |
| No `has_native_boolean_field` / `pattern_lookup_needs_param_pattern` base flags | Same behaviour as our values (`conditional_expression_supported_in_where_clause()` is always True; the pattern is always applied) | n/a |
| No `supports_inspectdb`, `supports_bit_aggregations`, `supports_on_delete_db_*` | Our False values are ignored; no tests in the supported modules depend on them | n/a |

### Django 5.2: what it lacks compared with 6.0

These come on top of the 6.0 table.

| Difference | Impact on the backend | Status |
|---|---|---|
| No general `StringAgg` (only in `contrib.postgres`) | **Blocker:** `expressions.py` imports it, so the backend would not load. Fix: import it conditionally through `compat.py`. Not supported on 5.2, and `contrib.postgres` is not patched. Known Limitations: "StringAgg requires Django 6.0+" ([DECISIONS](DECISIONS.md#2026-10-19-stringagg-requires-django-60-imported-through-compatpy)). `compat.StringAgg` is None on 5.2. | done (step B PR 7) |
| No `supports_tuple_comparison_against_subquery` check | 5.2 writes a row-value `>`/`<` comparison against a subquery, which Db2 for i rejects (SQL0115, probe `tuple_lookups`). The tuple hook raises the same `NotSupportedError` as 6.0+ (`compat.DJANGO_CHECKS_TUPLE_SUBQUERY_COMPARISON`), with an offline test on every version. | done (step B PR 7) |
| `sql_delete_column` ends in `CASCADE` | How Db2 for i handles `DROP COLUMN ... CASCADE` **can only be verified on IBM i**. A QTEMP probe comes first; then the same SQL is pinned for all versions ([DECISIONS](DECISIONS.md#2026-10-19-drop-column-sql-pinned-for-every-version-after-a-qtemp-probe)). Probe 23: all forms are valid and cancelled by CPA32B2 before any dependency handling; the default is not determinable on PUB400 (IBMI_NOTES). `schema.py` pins 6.0+'s text without a keyword; golden `ddl/remove_field`. | done (step B PR 8) |
| `return_insert_columns()` / `fetch_returned_insert_rows()` / `fetch_returned_insert_columns()` instead of `returning_columns()` / `fetch_returned_rows()` | No RETURNING support yet; compat provides both names when it comes | later (phase 5) |
| A collapsed `Case` does not cast its `Value` default | Our `Case` hook also casts 5.2's plain `NULL`; the 5.2 goldens equal 6.0's ([#117](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/117)) | checked |
| `IExact` / `PatternLookup.process_rhs` assign to `params[0]` (lists) | No backend hook passes tuple params into those paths: `lookup` passes on 5.2 (100 tests, the release run), the pattern and `iexact` goldens equal 6.0's | checked |
| No `AnyValue`, `Aggregate(order_by=...)`, `can_return_rows_from_update` | Our flags (`supports_any_value`, `supports_aggregate_order_by_clause`) are ignored on 5.2 | n/a |

## compat.py

`django_db2_for_i/compat.py` is the only module with `django.VERSION` checks
([DECISIONS](DECISIONS.md#2026-10-19-compatpy-in-three-sections-60-only-52-only-before-61)).
It defines `DJANGO_SERIES` and has three sections, each with its removal rule
in its heading; an offline test (`tests/offline/test_axes.py`) fails on a
Django version check anywhere else in the package. The sections fill as the
steps of phase 3 find real differences:

| Section | Holds | Deleted when |
|---|---|---|
| Django 6.0 only | nothing known yet | 6.0 is dropped |
| Django 5.2 only | `StringAgg` (None on 5.2), `DJANGO_CHECKS_TUPLE_SUBQUERY_COMPARISON`, `PASSING_ON_THIS_VERSION` (two `schema` expected failures that pass on 5.2, [DECISIONS](DECISIONS.md#2026-10-24-the-first-per-version-expected-failure-list)) | 5.2 is dropped |
| Before 6.1 (6.0 and 5.2) | `install_duration_adapter()` (the duration range check, [DECISIONS](DECISIONS.md#2026-10-20-the-duration-range-check-before-django-61)) | both are dropped |

**Dropping a version** means deleting its section, its entries in the
per-version lists, `tests/offline/golden/<version>/`, its line in
`DJANGO_PYTHONS` (noxfile) and its range in `pyproject.toml`, then updating
this file.

## Testing per version
The four test sets are described in [CONTRIBUTING.md](../CONTRIBUTING.md#test-sets).
- **Offline · own tests:** every Python × every supported Django version, in CI.
- **IBM i · own tests:** for every backend change, on each Django version the change touches.
- **IBM i · Django test suite:** before every release, the release run per Django version
  (`scripts/pub400.sh release_run <django>`, [DECISIONS](DECISIONS.md#2026-10-19-the-release-run-as-one-nox-session));
  it also captures the offline query corpus.
- **Offline · Django test suite (replay):** the corpus of every supported version, in CI.
- **Goldens:** all goldens of every series are verified on PUB400 (the `DROP COLUMN`
  golden stays unverified there: CPA32B2).
