# Phase 3: Django 5.2 support

> Status: Proposed, not yet approved

This is a plan, not a record. It follows the phase template in
`docs/phases/README.md`, added by [#85](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/85).
The analysis compares Django `stable/5.2.x` (`cae7247`, 2026-10-08, version
5.2.19 alpha) with the `stable/6.1.x` checkout used for the Django test runs,
against the backend on `main` at `18eded3`.

## Goal
From CLAUDE.md section 9: build `compat.py` from real differences, extend the
nox matrix, fill `DJANGO_VERSIONS.md`.

From CLAUDE.md section 3: support Django 5.2 LTS next to 6.1, on Python 3.12,
3.13 and 3.14. No `django.VERSION` check outside `compat.py`. Write it so that
dropping 5.2 later means deleting one block.

Proposed "done when":
- the backend imports and passes the offline tier on every Python × Django
  combination, with goldens for 5.2;
- the pub400 tier passes on 5.2;
- the release run (see "Test strategy") passes on 5.2 and 6.1;
- `docs/DJANGO_VERSIONS.md` records the backend API impact of both versions.

## What was done
Nothing yet. The proposed work follows.

### 1. Impact of the "Database backend API" notes for 6.0 and 6.1
Support goes back from 6.1 to 5.2, so every item added in 6.0 or 6.1 is
something 5.2 lacks or does differently. The "Uses it" column comes from grepping
`django_db2_for_i/`.

| Version | Item | Uses it | What it means for 5.2 |
|---|---|---|---|
| 6.0 | `BaseDatabaseSchemaEditor.sql_delete_column` no longer ends in `CASCADE` | `schema.py` does not override it | On 5.2, `DROP COLUMN` gets `CASCADE`. How Db2 for i handles `DROP COLUMN ... CASCADE` has not been probed. Proposal: set `sql_delete_column` in `schema.py` to the 6.x text for both versions (no compat needed), and add a DDL golden. |
| 6.0 | `return_insert_columns()` / `fetch_returned_insert_rows()` renamed to `returning_columns()` / `fetch_returned_rows()`; `fetch_returned_insert_columns()` removed | no (no RETURNING yet, phase 5) | None now. Phase 5 must provide both names, through compat. |
| 6.0 | `can_return_rows_from_update` added | no (default False) | None. |
| 6.0 | `field_cast_sql()` removed | no | None. |
| 6.0 | `as_sql()` params should be tuples ("Custom ORM expressions should return params as a tuple") | `expressions.py` and `compiler.py` return lists and tuples | 5.2 still changes params in place in some lookups (`IExact.process_rhs` and `PatternLookup.process_rhs` assign to `params[0]`). Check that no hook passes a tuple into those paths on 5.2. |
| 6.0 (Models) | `StringAgg`, `AnyValue` and `Aggregate(order_by=...)` become general | `expressions.py` imports `StringAgg` from `django.db.models` | **Blocker:** on 5.2 that import raises `ImportError`, so the backend does not load at all. In 5.2, `StringAgg` exists only in `django.contrib.postgres.aggregates`. Belongs in compat (see Design). `supports_any_value` and `supports_aggregate_order_by_clause` are harmless on 5.2. |
| 6.0 | `DEFAULT_AUTO_FIELD` defaults to `BigAutoField` | test settings set `AutoField` explicitly | None. |
| 6.1 | `adapt_durationfield_value()` hook added | `operations.py` overrides it (BIGINT range check, [#57](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/57)) | On 5.2, `DurationField.get_db_prep_value()` returns `duration_microseconds(value)` and never calls the hook. Values still arrive as microseconds, but the range check is skipped: an out-of-range duration fails in the driver instead of raising the backend's clear `ValueError`. Needs a 5.2-only path in compat (open question 3). |
| 6.1 | `get_relations()` returns 3-tuples with `db_on_delete` | not implemented (`can_introspect_foreign_keys = False`) | Phase 4: compat shapes the tuple per version. |
| 6.1 | `supports_inspectdb` added | set to False | 5.2 ignores it, so `inspectdb` tests would run there. Not in the module set, so no impact now. Phase 4. |
| 6.1 | `prohibits_dollar_signs_in_column_aliases` removed | no | None. |
| 6.1 | `binary_placeholder_sql(value, compiler)` returns `(sql, params)` | no (a bytes `Value` is refused) | Compat item for when binary values are supported. |
| 6.1 | `get_geom_placeholder()` renamed | no (GIS) | None. |
| 6.1 | `supports_bit_aggregations` added | set to False | None. In 5.2, `BitAnd` etc. are in `contrib.postgres` only. |
| 6.1 (Models) | Table, JOIN and annotation aliases are quoted systematically (`SQLCompiler.quote_name()` replaces `quote_name_unless_alias()`) | `compiler.py` calls neither | The generated SQL text differs, so 5.2 needs its own goldens (`tests/offline/golden/5.2/...`). Our `quote_name()` uppercases, and unquoted aliases fold to uppercase, so the identifiers should be the same. This must be checked in the goldens, not assumed. |
| 6.1 (Models) | Default model ordering applies to combined querysets | compound queries ([#80](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/80)) | Different SQL and results on 5.2. Goldens per series; the pub400 tests must not assume either behaviour. |
| 6.1 (Models) | DB-level `on_delete` (`DB_CASCADE`, ...) and `supports_on_delete_db_*` | flags set to False | None in phase 3. CLAUDE.md already plans DB-level `on_delete` as a 6.1+ feature (phase 6). |
| 6.1 | `Field.get_placeholder()` deprecated in favour of `get_placeholder_sql()` | no | None now. |

### 2. Code differences, `stable/5.2.x` → `stable/6.1.x`
Changed lines (approximate, from `diff -u`, comment rewraps included): `base/operations.py` 175,
`base/schema.py` 133, `base/creation.py` 87, `base/features.py` 65,
`base/base.py` 21, `base/introspection.py` 20, `sql/compiler.py` 298,
`fields/tuple_lookups.py` 35, `fields/related_lookups.py` 13 (comments only).

**Compiler methods the backend overrides** (method-by-method comparison):
- Unchanged: `SQLCompiler.compile`, `pre_sql_setup`, `get_extra_select`,
  `get_group_by`, `get_order_by`, `get_combinator_sql`,
  `_get_combinator_part_sql`.
- `SQLCompiler.as_sql`: one comment line only. Both versions write the
  `SELECT * FROM (` wrapper for ordered compound queries that the backend
  replaces with `SELECT * FROM LATERAL (`.
- `get_from_clause` and `SQLDeleteCompiler._as_sql`: `quote_name()` replaces
  `quote_name_unless_alias()`, so only the alias quoting differs. Our overrides
  call `super()` and need no compat.
- `get_combinator_sql` and `_get_combinator_part_sql` are not overridden on
  `main` today (the compound query flags of #80 needed no override). They are
  the same in both versions, so a later override would not need compat either.
- Other changes that do not touch the backend's overrides:
  - `SQLInsertCompiler.as_sql` handles `db_default` per column in bulk inserts
    (6.x). This matters when `has_bulk_insert` is enabled (phase 5).
  - `SQLUpdateCompiler` gains `RETURNING` support.
  - `field_as_sql` uses `get_placeholder_sql`.
  - `execute_sql` closes the cursor more safely.

**`base/features.py`**: flags in 6.1 that 5.2 does not have. Extra
attributes are ignored on 5.2, so setting them is harmless, with the
behaviour differences below:
- `has_native_boolean_field`: a base flag only in 6.x, where
  `conditional_expression_supported_in_where_clause()` uses it. 5.2's version
  always returns True, which matches what our flag (True from
  `has_boolean_type`) gives on 6.1.
- `pattern_lookup_needs_param_pattern`: 5.2 always applies the pattern, the
  same as our value True.
- `supports_tuple_comparison_against_subquery`: 6.1 raises
  `NotSupportedError` for `>`, `>=`, `<`, `<=` of a tuple against a subquery
  when it is False (our value). 5.2 has no such check: Django writes a
  row-value comparison, which Db2 for i rejects (SQL0115, probe
  `tuple_lookups`). The 5.2 result is a database error instead of
  `NotSupportedError`. Proposal: `tuple_expanded_as_db2_for_i` raises the same
  `NotSupportedError` when compat says the Django version lacks the check.
- Also new, all harmless: `supports_aggregate_order_by_clause`,
  `supports_aggregate_distinct_multiple_argument`, `supports_any_value`,
  `supports_bit_aggregations`, `supports_default_in_bit_aggregations`,
  `supports_json_negative_indexing`, `supports_alter_generated_column_data_type`,
  `supports_no_precision_decimalfield`, `supports_on_delete_db_*`,
  `supports_inspectdb`, `can_return_rows_from_update`, `supports_uuid4/7_*`.

**`base/operations.py`**: added in 6.x are `adapt_durationfield_value`,
`returning_columns`, `fetch_returned_rows`, `fk_on_delete_sql`,
`convert_trunc_expression`, `format_debug_sql`, `compile_json_path`, and
`format_json_path_numeric_index`. Removed are `return_insert_columns`,
`fetch_returned_insert_columns` and `field_cast_sql`. `binary_placeholder_sql`
and `bulk_batch_size` changed. Of these, the backend overrides only
`adapt_durationfield_value` (see section 1).

**`base/schema.py`**: `sql_delete_column` (no `CASCADE`), on-delete SQL in
`sql_create_fk`, `add_field` and `table_sql`, and the inline comment moved to
the end of `_iter_column_sql`. Our `_iter_column_sql` filters `DEFAULT NULL`
from the parts, which works with either order (`supports_comments_inline` is
not set). Unchanged: `execute`, `prepare_default`, `db_default_sql`,
`column_sql`, `create_model`, `delete_model`, `remove_field`.

**`base/creation.py`**: the methods we override (`_create_test_db`,
`_destroy_test_db`, `_clone_test_db`, `_get_test_db_name`) are unchanged.
`mark_expected_failures_and_skips` is different: 6.1's `_mark_test` falls
back when an import fails, while 5.2 calls `import_string` and `getattr` directly and raises
for a test name that does not exist in its suite.
**Consequence:** the skip and expected-failure lists must be per Django
version. A 6.1-only test name in the list breaks every 5.2 run at setup.

**Expressions and lookups the backend patches** (`as_db2_for_i`; outside the
requested diff, checked because the hooks depend on them):
- `Case.as_sql`: in 6.1, a collapsed `Case` casts its `Value` default. Our
  `case_as_db2_for_i` handles the 5.2 form (plain `NULL`) too.
- `Value.as_sql`: uses `get_placeholder_sql` and tuple params in 6.1.
- `Aggregate.as_sql`: reworked in 6.0 (`AggregateFilter`, `order_by`). The
  `filter=` emulation that [#37](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/37)
  depends on needs 5.2 goldens.
- `fields/tuple_lookups.py`: the subquery check above, plus an SQLite-only
  change.
- `fields/related_lookups.py`: comments only.

**What goes into `compat.py`** (each one with a test):
1. `StringAgg`: the general class on 6.x, `None` on 5.2 (open question 1).
2. Whether Django checks tuple comparisons against subqueries (6.1: yes).
3. Whether Django calls `adapt_durationfield_value` (6.1: yes).
4. The per-version skip and expected-failure lists, or a filter that drops
   names a version lacks.
5. `DJANGO_SERIES` (exists) for golden paths.

Later phases add the `returning_columns` / `fetch_returned_rows` names
(phase 5), `get_relations` tuples (phase 4) and `binary_placeholder_sql`.

### 3. Python 3.14 and the minimum 5.2 patch release
`docs/releases/5.2.8.txt`, lines 7–9:

> Django 5.2.8 fixes one security issue with severity "high", one security issue
> with severity "moderate", and several bugs in 5.2.7. It also adds compatibility
> with Python 3.14.

This matches `docs/DJANGO_VERSIONS.md` (3.14 from 5.2.8). Later patch releases
fix more 3.14 bugs: 5.2.9 (a crash with template tag functions), 5.2.10
("one bug related to support for Python 3.14") and 5.2.12 ("one bug related to
support for Python 3.14"). See open question 2.

### 4. Design
- **`compat.py`**: the only `django.VERSION` check. One section per version,
  each starting with `# --- Django 5.2 (remove when 5.2 is dropped) ---`,
  exporting names (`StringAgg`, `DJANGO_CHECKS_TUPLE_SUBQUERY_COMPARISON`,
  `DJANGO_CALLS_ADAPT_DURATIONFIELD_VALUE`, ...) that other modules import.
  Dropping 5.2 means deleting that block and the code paths behind its
  names. An offline test asserts that `django.VERSION` appears only in
  `compat.py`.
- **`pyproject.toml`**: one specifier for both series,
  `"Django>=5.2.8,!=6.0.*,<6.2"` (there is no 5.3), and the
  `Framework :: Django :: 5.2` classifier. The lower bound depends on open
  question 2.
- **nox matrix**: `DJANGO_PYTHONS = {"5.2": ["3.12", "3.13", "3.14"], "6.1":
  [...]}`. The offline tier covers every Python × every Django version (6
  sessions). `pub400` and `django_tests` get a Django version parameter,
  defaulting to the newest. CI runs the full offline matrix.
- **Goldens**: `tests/offline/golden/5.2/7.5/...`, generated, reviewed and then
  verified on PUB400 with the pub400 tier's golden job on 5.2.
- **`docs/DJANGO_VERSIONS.md` outline**: Python support table (exists).
  Then, per version, the "Database backend API" items with impact and status
  (sections 1–2 of this plan for 6.1/6.0, and the 5.2 notes' own section).
  Then a list of what compat.py covers and how to drop a version.
- **Badges and status** (owned by the main session; described here, not
  edited): `docs/status.toml` `[versions] django` changes from
  `"6.1 | 5.2 planned"` to `"6.1 | 5.2"`, and phase 3 moves to "in progress",
  then "done". `TEST_STATUS.md` says each row of test badges is one Django version's
  runs, so 5.2 logs in `test-results/5.2/` should add a second row
  (`Django 5.2 · Python 3.14 on PUB400`), with its own modules badge. Whether
  the script needs changes for that is for the main session to check. `TEST_STATUS.md` then shows each module once
  per version.

### 5. Test strategy
- **Offline tier**: every Python × every Django version (CLAUDE.md version
  matrix), on every commit and in CI, with goldens per Django series.
- **pub400 tier during development**: `nox -s pub400` on Django 5.2 (newest
  Python) for every backend PR in this phase, plus 6.1 as now. One connection,
  sequential.
- **Release run** (new policy, before every release): for every supported
  Django version, with the newest Python, run all supported Django modules
  (the modules in [TEST_STATUS.md](../TEST_STATUS.md): `aggregation`, `basic`,
  `expressions`, `lookup`, `ordering`, `queries` as its labels, and
  `transactions`), plus the pub400 tier. The run is sequential, uses one
  connection, runs off-peak, and is never the full Django suite.
  `scripts/runtests.sh` takes at most three labels per call, so the run is a
  fixed list of calls; a small script could drive it (open question 5).
- **Full tier** (all of `runtests.py`, the full matrix): only on a dedicated
  IBM i, as CLAUDE.md says.

### 6. Proposed order of PRs
1. `docs`: fill `DJANGO_VERSIONS.md` (sections 1–3 of this plan).
2. `feat(compat)`: the 5.2 compat block (`StringAgg`, tuple subquery check,
   duration range check), the per-version skip and expected-failure lists, and
   the `django.VERSION` guard test. No behaviour change on 6.1.
3. `fix(schema)`: `sql_delete_column` without `CASCADE`, plus a DDL golden.
   This may need a QTEMP probe of `DROP COLUMN ... CASCADE` first.
4. `build`: pyproject range, nox matrix (offline × 5.2, Django parameter for
   `pub400` / `django_tests`), CI.
5. `test`: 5.2 goldens, verified on PUB400, and pub400 tier fixes for 5.2.
6. `test`: Django modules on 5.2 (one module per run), shrinking the 5.2
   lists. The main session updates `status.toml` and regenerates badges.
7. `docs`: user docs (supported versions, the 5.2 limitations such as
   `StringAgg`), the phase 3 record and the changelog.

## Key decisions
None yet. These need the maintainer's decision, one per question:

1. **`StringAgg` on 5.2**: leave it unsupported (5.2 has only the PostgreSQL
   class in `contrib.postgres`), or also patch that class?
2. **Minimum 5.2 patch release**: 5.2.8 (adds Python 3.14), or a later one
   with the 3.14 bug fixes (5.2.12) or the newest security release?
3. **Duration range check on 5.2**: keep it through a 5.2-only hook (for
   example a `DurationField.get_db_prep_value` wrapper registered from
   compat), or accept the driver's `OverflowError` on 5.2?
4. **`DROP COLUMN ... CASCADE`**: pin the 6.x text for both versions without
   a probe, or probe Db2 for i's behaviour in QTEMP first?
5. **Release run**: CLAUDE.md section 6 still says "Full matrix: ... before
   every release". Should CLAUDE.md be updated to the release-run policy, and
   should the release run be one nox session or a documented list of
   `runtests.sh` calls?
6. **Phase order**: start phase 3 only after phase 2 is done (the `queries`
   module is still partial), or in parallel?
7. **Golden verification on 5.2**: verify every 5.2 golden on PUB400, or only
   those whose SQL differs from 6.1?

## IBM i findings
None expected: phase 3 is about the Django version, not the server. The one
open IBM i question is `DROP COLUMN ... CASCADE` (question 4). A probe would be
proposed first, QTEMP only.

## Test status at the end of the phase
Not started. Baseline on 6.1 at `18eded3`: see
[TEST_STATUS.md](../TEST_STATUS.md) (7 modules with runs on PUB400; offline
tier passing on Python 3.12–3.14 × Django 6.1).

## Carried forward
- Into phase 3: Django 5.2 support was listed in the phase 1 wrap-up
  ([#16](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/16))
  as needing a dedicated IBM i for the full tier. On PUB400, the release run
  above is the limit.
- From phase 3 to later phases:
  - compat names for `returning_columns` / `fetch_returned_rows` (phase 5);
  - `get_relations` 3-tuples and `supports_inspectdb` (phase 4);
  - `binary_placeholder_sql` (when binary values are supported);
  - DB-level `on_delete`, 6.1 only (phase 6).
- Open issues that touch both versions: [#69](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/69),
  [#75](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/75),
  [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82).

## Links
- [docs/DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md), [CLAUDE.md](../../CLAUDE.md)
  sections 3, 4, 6 and 9.
- Django release notes: `docs/releases/6.0.txt` and `6.1.txt` ("Database
  backend API"), `docs/releases/5.2.txt` and `5.2.8.txt`.
- `django_db2_for_i/compat.py`, `compiler.py`, `expressions.py`,
  `operations.py`, `features.py`.
