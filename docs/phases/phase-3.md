# Phase 3: Django 6.0 and 5.2 support

> Status: Proposed, not yet approved

This is a plan, not a record. It follows the phase template in
`docs/phases/README.md`, added by [#85](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/85).
The version policy (5.2 LTS, 6.0 and 6.1) and the phase name come from
[#88](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/88).

The analysis compares three Django checkouts:

| Branch | Commit | Version |
|---|---|---|
| `stable/6.1.x` | the one used for the Django test runs | 6.1.3 alpha |
| `stable/6.0.x` | `52e5ba1`, 2026-10-08 | 6.0.10 alpha |
| `stable/5.2.x` | `cae7247`, 2026-10-08 | 5.2.19 alpha |

They are compared against the backend on `main` at `18eded3`.

## Goal
From CLAUDE.md section 9, as proposed in #88: work backwards in two steps,
6.1 → 6.0 first, then 6.0 → 5.2. Build `compat.py` from real differences,
extend the nox matrix, fill `DJANGO_VERSIONS.md`.

From CLAUDE.md sections 3 and 4: Python 3.12, 3.13 and 3.14 on every
supported Django version. No `django.VERSION` check outside `compat.py`.

Proposed "done when", per step (6.0, then 5.2):
- the backend imports and passes the offline tier on every Python × that
  Django version, with goldens for that series;
- the pub400 tier passes on that version;
- `docs/DJANGO_VERSIONS.md` records the backend API impact.

At the end of the phase, the release run passes on 5.2, 6.0 and 6.1.

## What was done
Nothing yet. The proposed work follows.

### 1. Supported versions, Python and minimum patch releases

| Django | Python (release notes) | Minimum patch for Python 3.14 | End of security support |
|---|---|---|---|
| 6.1 | 3.12, 3.13, 3.14 | 6.1.0 | December 2027 |
| 6.0 | 3.12, 3.13, 3.14 | 6.0.0 | **April 2027** |
| 5.2 LTS | 3.10–3.14 (3.14 from 5.2.8) | 5.2.8 | April 2028 |

Sources:
- **6.0**, `docs/releases/6.0.txt` line 21: "Django 6.0 supports Python 3.12,
  3.13, and 3.14." Later patches fix bugs that occur on 3.14:
  - `6.0.1.txt`: "Fixed a bug where management command colorized help
    (introduced in Python 3.14) ignored the `--no-color` option ...";
  - `6.0.3.txt`: "Fixed `NameError` when inspecting functions making use of
    deferred annotations in Python 3.14".
- **5.2**, `docs/releases/5.2.8.txt` lines 7–9: "Django 5.2.8 fixes one
  security issue with severity "high", one security issue with severity
  "moderate", and several bugs in 5.2.7. It also adds compatibility with
  Python 3.14." `5.2.txt`: "Django 5.2 supports Python 3.10, 3.11, 3.12, 3.13,
  and 3.14 (as of 5.2.8)." Later 3.14 fixes are in 5.2.9, 5.2.10 ("one bug
  related to support for Python 3.14") and 5.2.12 (the same wording).
- **End of security support**: djangoproject.com/download, "Supported
  versions" table, checked 2026-10-19. 6.0: end of mainstream support
  "August 4, 2026", end of extended support "April 2027". 5.2 LTS: "April
  2028". 6.1: "December 2027". These dates are from the web page, not from
  the release notes.
- **Order of dropping**: 6.0 reaches end of life before 5.2. Under the policy
  it is dropped in the first release after April 2027, while 5.2 stays
  until April 2028. The compat design below takes this into account.

### 2. Impact of the "Database backend API" notes
The "Uses it" column comes from grepping `django_db2_for_i/`. An item
introduced in 6.1 is missing in both 6.0 and 5.2. An item introduced in 6.0
is missing in 5.2 only.

**Introduced in 6.1 (affects the 6.0 step and 5.2):**

| Item | Uses it | Impact |
|---|---|---|
| `adapt_durationfield_value()` hook | `operations.py` overrides it (BIGINT range check, [#57](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/57)) | Never called on 6.0 or 5.2: `DurationField.get_db_prep_value()` returns `duration_microseconds(value)` itself. Values still arrive as microseconds, but out-of-range durations fail in the driver instead of raising the backend's `ValueError`. Open question 3. |
| `get_relations()` 3-tuples with `db_on_delete` | not implemented yet | Phase 4: compat shapes the tuple. |
| `supports_inspectdb`, `supports_bit_aggregations`, `supports_on_delete_db_*` | set to False | Ignored before 6.1: harmless. DB-level `on_delete` stays 6.1+ (phase 6). |
| `prohibits_dollar_signs_in_column_aliases` removed | no | None. |
| `binary_placeholder_sql(value, compiler)` returns `(sql, params)` | no | Compat item for when binary values are supported. |
| Aliases quoted systematically (`SQLCompiler.quote_name()`; `quote_name_unless_alias()` deprecated) | `compiler.py` calls neither | SQL text differs, so 6.0 and 5.2 need their own goldens. Our `quote_name()` uppercases, and unquoted aliases fold to uppercase, so the identifiers should match. To be checked in the goldens, not assumed. |
| Default model ordering applied to combined querysets | compound queries ([#80](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/80)) | Different SQL and results on 6.0 and 5.2: goldens per series. The pub400 tests must not depend on it. |
| `has_native_boolean_field` as a base flag | set (from `has_boolean_type`) | Before 6.1, `conditional_expression_supported_in_where_clause()` always returns True. Our True flag gives the same result on 6.1. No impact. |
| `pattern_lookup_needs_param_pattern` | set to True | Before 6.1 the pattern is always applied, the same as True. No impact. |
| `mark_expected_failures_and_skips` falls back on `ImportError` (`_mark_test`) | our skip / expected-failure lists | 6.0 and 5.2 use `import_string` + `getattr` directly and fail for a test name their suite lacks. The lists must be per Django version. |

**Introduced in 6.0 (affects 5.2 only):**

| Item | Uses it | Impact on 5.2 |
|---|---|---|
| `StringAgg`, `AnyValue`, `Aggregate(order_by=...)` become general | `expressions.py` imports `StringAgg` from `django.db.models` | **Blocker:** `ImportError` on 5.2, so the backend does not load. 5.2 has `StringAgg` only in `contrib.postgres`. Open question 1. |
| `sql_delete_column` without `CASCADE` | `schema.py` does not override it | 5.2 writes `DROP COLUMN ... CASCADE`. Db2 for i's handling is not probed. Open question 4. |
| `returning_columns()` / `fetch_returned_rows()` (renamed), `can_return_rows_from_update` | no (phase 5) | Phase 5 provides both names through compat. |
| `supports_tuple_comparison_against_subquery` | set to False | 5.2 does not raise `NotSupportedError`. It writes a row-value comparison against a subquery, which Db2 for i rejects (SQL0115, probe `tuple_lookups`). Proposal: our tuple hook raises the same error on 5.2. |
| Collapsed `Case` casts its `Value` default | `case_as_db2_for_i` | Our patch also handles 5.2's plain `NULL`. Goldens per series. |
| Params as tuples | `expressions.py`, `compiler.py` | 5.2 assigns to `params[0]` in `IExact` / `PatternLookup.process_rhs`. Check that no hook hands a tuple into those paths. |
| `field_cast_sql()` removed | no | None. |
| `DEFAULT_AUTO_FIELD` defaults to `BigAutoField` | test settings set `AutoField` | None. |

### 3. Code differences
Changed lines (approximate, from `diff -u`, comment rewraps included):

| File | 5.2 → 6.0 | 6.0 → 6.1 |
|---|---|---|
| `db/backends/base/base.py` | 6 | 15 |
| `db/backends/base/features.py` | 33 | 32 |
| `db/backends/base/operations.py` | 92 | 83 |
| `db/backends/base/schema.py` | 65 | 68 |
| `db/backends/base/introspection.py` | 11 | 15 |
| `db/backends/base/creation.py` | 39 | 50 |
| `db/models/sql/compiler.py` | 142 | 160 |
| `db/models/fields/tuple_lookups.py` | 29 | 6 |
| `db/models/fields/related_lookups.py` | 13 (comments) | 0 |

**Compiler methods the backend overrides**, compared method by method:
- The same in all three versions: `compile`, `pre_sql_setup`,
  `get_extra_select`, `get_group_by`, `get_order_by`.
- `get_combinator_sql` and `_get_combinator_part_sql` are also the same in all
  three, and are not overridden on `main`.
- `as_sql`: comment lines only. All three versions write the `SELECT * FROM (`
  wrapper that the backend turns into `SELECT * FROM LATERAL (`.
- `get_from_clause` and `SQLDeleteCompiler._as_sql`: the same in 5.2 and 6.0.
  In 6.1 they use `quote_name()` instead of `quote_name_unless_alias()`. Our
  overrides call `super()`, so no compat is needed.
- Other compiler changes that don't touch our overrides:
  - 6.0: `UPDATE ... RETURNING` (`SQLUpdateCompiler.execute_returning_sql`)
    and insert-returning through `fetch_returned_rows`.
  - 6.1: per-column `db_default` in bulk inserts (relevant for phase 5),
    `get_placeholder_sql`, and safer cursor closing.

**`base/features.py`**:
- New in 6.0: `supports_aggregate_order_by_clause`,
  `supports_aggregate_distinct_multiple_argument`, `supports_any_value`,
  `supports_json_negative_indexing`, `supports_tuple_comparison_against_subquery`,
  `can_return_rows_from_update`.
- New in 6.1: `has_native_boolean_field`, `pattern_lookup_needs_param_pattern`,
  `supports_alter_generated_column_data_type`, `supports_bit_aggregations`,
  `supports_default_in_bit_aggregations`, `supports_inspectdb`,
  `supports_no_precision_decimalfield`, `supports_on_delete_db_*`,
  `supports_uuid4/7_*`, `disallowed_simple_test_case_connection_methods`.
- Extra attributes are ignored by older versions. The behaviour differences
  are the ones in section 2.

**`base/operations.py`**:
- 6.0: `returning_columns` and `fetch_returned_rows` replace
  `return_insert_columns`, `fetch_returned_insert_rows` and
  `fetch_returned_insert_columns`; `field_cast_sql` is removed.
- 6.1: adds `adapt_durationfield_value`, `convert_trunc_expression` and
  `fk_on_delete_sql`, and changes `binary_placeholder_sql`, `bulk_batch_size`
  and `conditional_expression_supported_in_where_clause`.
- Of all these, the backend overrides only `adapt_durationfield_value`.

**`base/schema.py`**:
- 6.0: `sql_delete_column` without `CASCADE`.
- 6.1: on-delete SQL in foreign keys, and the inline comment moved to the end
  of `_iter_column_sql`. Our `_iter_column_sql` filters `DEFAULT NULL` and
  works with either order.
- The other methods we rely on are unchanged: `execute`, `prepare_default`,
  `db_default_sql`, `column_sql`, `create_model`, `delete_model`,
  `remove_field`.

**`base/creation.py`**: the methods we override (`_create_test_db`,
`_destroy_test_db`, `_clone_test_db`, `_get_test_db_name`) are unchanged. The
skip-marking difference is described in section 2. In 6.1,
`create_test_db(serialize=...)` is deprecated.

**`fields/tuple_lookups.py`**:
- 6.0: the subquery comparison check (section 2), plus lhs representation
  changes.
- 6.1: an SQLite-only change.

**`fields/related_lookups.py`**: comment changes only.

### 4. Design
**`compat.py`.** The only `django.VERSION` checks. It exports named facts,
which other modules import, for example:
- `DJANGO_CALLS_ADAPT_DURATIONFIELD_VALUE` (6.1+);
- `DJANGO_CHECKS_TUPLE_SUBQUERY_COMPARISON` (6.0+);
- `StringAgg` (6.0+, `None` on 5.2);
- `DJANGO_SERIES` (exists).

6.0 is dropped before 5.2, so "one place to delete" cannot simply mean one
block per version. Proposed sections, each with its removal rule in a
heading comment:
1. `# --- Django 6.0 only (delete when 6.0 is dropped) ---`: shims needed
   only by 6.0. None known yet.
2. `# --- Django 5.2 only (delete when 5.2 is dropped) ---`: `StringAgg`, the
   tuple subquery check, and anything else from section 2's 6.0 table.
3. `# --- Before 6.1: Django 6.0 and 5.2 (delete when both are dropped) ---`:
   the duration hook, and the per-version test lists with no 6.1-only names.

Dropping 6.0 (after April 2027) means deleting section 1, the 6.0 entries in
the per-version lists, `tests/offline/golden/6.0/`, and the `"6.0"` line in
the noxfile; section 3 then serves 5.2 alone. Dropping 5.2 (after April
2028) deletes sections 2 and 3. An offline test asserts that
`django.VERSION` appears only in `compat.py`. Open question 5.

**Packaging and nox:**
- `pyproject.toml`: `"Django>=5.2.8,<6.2"` (5.2, 6.0 and 6.1; there is no
  5.3), with the classifiers `Framework :: Django :: 5.2 / 6.0 / 6.1`.
- `noxfile.py`: `DJANGO_PYTHONS` gets `"6.0"` (step A) and `"5.2"` (step B),
  each with 3.12, 3.13 and 3.14. The offline tier then covers every Python ×
  every Django version (9 sessions).
- `pub400` and `django_tests` get a Django version parameter, defaulting to
  the newest.
- CI ([#87](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/87))
  reads the combinations from the noxfile, so each new version adds its
  parallel jobs without a workflow change.

**Goldens:** `tests/offline/golden/6.0/7.5/...` and `.../5.2/7.5/...`,
generated, reviewed, and verified on PUB400 by the pub400 tier's golden job
on that version.

**`docs/DJANGO_VERSIONS.md` outline:**
- the table of section 1;
- per version, the "Database backend API" items with impact and status
  (sections 2–3 of this plan);
- what `compat.py` covers, and the steps for dropping 6.0 and 5.2.

**Badges and status.** These are owned by the main session; described here,
not edited:
- `docs/status.toml` `[versions] django` becomes `"6.1 | 6.0 | 5.2"`, and
  phase 3 moves to "in progress", then "done".
- `TEST_STATUS.md` says each row of test badges is one Django version's runs,
  so logs in `test-results/6.0/` and `test-results/5.2/` should add a row per
  version. Whether the script needs changes for that is for the main session
  to check.

### 5. Test strategy
- **Offline tier**: every Python × every Django version (9 combinations), on
  every commit, as parallel CI jobs. CI never connects to an IBM i.
- **pub400 tier during development**: the full tier on each Django version
  that the step touches, newest Python, for every backend PR. Step A runs 6.0
  and 6.1; step B runs 5.2, 6.0 and 6.1. One connection, sequential.
- **Django modules during development**: single modules or labels, as now,
  on the version being added.
- **Release run**, before every release (#88): for 5.2, 6.0 and 6.1, with the
  newest Python, all supported Django modules (the modules in
  [TEST_STATUS.md](../TEST_STATUS.md): `aggregation`, `basic`, `expressions`,
  `lookup`, `ordering`, `queries` as its labels, and `transactions`) plus the
  pub400 tier. The run is sequential, uses one connection at a time, runs
  preferably off-peak, and is never the full Django suite.
  `scripts/runtests.sh` takes at most three labels per call, so the run is a
  fixed list of calls per version (open question 7).
- **Full tier**: only on a dedicated IBM i.

### 6. Plan with PR boundaries

**Step A: 6.1 → 6.0**
1. `docs`: `DJANGO_VERSIONS.md`, the 6.0 and 6.1 sections (sections 1–3 of
   this plan).
2. `feat(compat)`: `compat.py` sections and the `django.VERSION` guard test.
   - The duration range check for versions before 6.1.
   - Per-version skip and expected-failure lists.
   - No behaviour change on 6.1.
3. `build`: `"6.0"` in the noxfile and the pyproject range up to 6.0, plus
   the Django parameter for `pub400` / `django_tests`.
4. `test`: 6.0 goldens, verified on PUB400; pub400 tier fixes for 6.0.
5. `test`: the supported Django modules on 6.0, one per run, shrinking the
   6.0 lists. The main session updates `status.toml` and the badges.

**Step B: 6.0 → 5.2**
6. `docs`: `DJANGO_VERSIONS.md`, the 5.2 section.
7. `feat(compat)`: the 5.2 section (`StringAgg`, the tuple subquery check).
8. `fix(schema)`: `sql_delete_column` without `CASCADE` for all versions,
   with a DDL golden. This may need a QTEMP probe first (open question 4).
9. `build`: `"5.2"` in the noxfile, pyproject `>=5.2.8`.
10. `test`: 5.2 goldens and pub400 tier fixes.
11. `test`: the supported Django modules on 5.2.

**Close**
12. `docs`: user docs (supported versions, version-specific limitations),
    the phase 3 record, the changelog, and a release run on all three
    versions before the next release.

## Key decisions
None yet. The decisions are in the open questions at the end.

## IBM i findings
None expected: phase 3 is about the Django version axis. The one open IBM i
question is `DROP COLUMN ... CASCADE` (question 4). A probe would be proposed
first and would use QTEMP only.

## Test status at the end of the phase
Not started. Baseline on 6.1 at `18eded3`: see
[TEST_STATUS.md](../TEST_STATUS.md) (7 modules with runs on PUB400; offline
tier passing on Python 3.12–3.14 × Django 6.1).

## Carried forward
- From phase 3 to later phases:
  - compat names for `returning_columns` / `fetch_returned_rows` (phase 5);
  - `get_relations` 3-tuples and `supports_inspectdb` (phase 4);
  - `binary_placeholder_sql` (when binary values are supported);
  - DB-level `on_delete`, 6.1+ (phase 6).
- When 6.2 LTS ships, the same steps apply forwards.
- Open issues that touch every version: [#69](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/69),
  [#75](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/75),
  [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82).

## Links
- [docs/DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md), [CLAUDE.md](../../CLAUDE.md)
  sections 3, 4, 6 and 9; #87 (CI matrix), #88 (policies).
- Django release notes: `docs/releases/5.2.txt`, `5.2.8.txt`, `6.0.txt`,
  `6.0.1.txt`, `6.0.3.txt`, `6.1.txt` ("Database backend API").
- djangoproject.com/download ("Supported versions").

## Open questions for the maintainer
1. **`StringAgg` on 5.2**: leave it unsupported (5.2 has only the PostgreSQL
   class in `contrib.postgres`), or also patch that class?
2. **Minimum patch releases**: what should the minimums be?
   - 5.2: 5.2.8 (first with 3.14) or 5.2.12 (the latest 3.14 fix)?
   - 6.0: 6.0.0 or 6.0.3?
   - Or always the newest security release?
3. **Duration range check before 6.1**: keep it on 6.0 and 5.2 through a
   compat hook (for example wrapping `DurationField.get_db_prep_value`), or
   accept the driver's `OverflowError` there?
4. **`DROP COLUMN ... CASCADE`** (5.2): pin the 6.x text for all versions
   without a probe, or probe Db2 for i's behaviour in QTEMP first?
5. **compat structure**: is the three-section layout (6.0 only, 5.2 only,
   before 6.1) right, given that 6.0 is dropped a year before 5.2?
6. **Timing**: start step A only after phase 2 is done (`queries` is still
   partial), or in parallel?
7. **Release run**: one nox session that runs the whole list, or a
   documented list of `runtests.sh` calls?
8. **Golden verification**: verify every 6.0 and 5.2 golden on PUB400, or
   only those whose SQL differs from 6.1?
