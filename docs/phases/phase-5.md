# Phase 5: Returning & bulk

> Status: Done (2026-10-31)

## Goal
From CLAUDE.md section 9: **returning & bulk**: `FINAL TABLE` returning
columns, `bulk_create`, unique constraint variants, partial / expression /
covering indexes; the `constraints`, `indexes` and `model_indexes` modules
(the phase 4/5 boundary: [DECISIONS](../DECISIONS.md#2026-10-21-phase-4-and-phase-5-schema-needs-first-constraint-and-index-variants-later)).

"Done when" (approved, answer b), all met:
- `bulk_create`, `constraints`, `indexes` and `model_indexes` run on 6.1, 6.0
  and 5.2 against PUB400 without failures or errors, and join the supported
  modules.
- No flag is `planned = "phase 5"` in [features.toml](../features.toml): each
  is on, with an own IBM i test of the real-world pattern, or off with a
  reason.
- Goldens for every new SQL shape, per Django series, all verified on PUB400.
- The probe results decisions rest on are in IBMI_NOTES and `probes/results/`.

## What was done

**Step 0: probes and the baseline**
- QTEMP probes `qtemp_returning`, `qtemp_bulk`, `qtemp_indexes`,
  `qtemp_unique_nulls`, `qtemp_cursors`; a baseline of the four modules on 6.1
  at the beta tag. The flags that stay off were decided here.
  [#212](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/212)

**Names**
- `truncates_names`; `supports_sequence_reset`, with
  `sequence_reset_by_name_sql()`.
  [#214](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/214)

**Step A: returning and bulk insert**
- `can_return_columns_from_insert`, `supports_default_keyword_in_insert`,
  `allows_auto_pk_0`: the key and `db_default` values come from
  `SELECT ... FROM FINAL TABLE (INSERT ...)`.
  [#215](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/215)
- `has_bulk_insert`, `can_return_rows_from_bulk_insert` (with `ORDER BY INPUT
  SEQUENCE`), `supports_default_keyword_in_bulk_insert`; a `bulk_batch_size()`
  of its own, the same on every Django version: at most 16,000 markers, 16,000
  rows and 512 LOB markers per statement.
  [#216](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/216)

**Step C: partial and expression indexes** (#216)
- `supports_partial_indexes`, `supports_functions_in_partial_indexes`,
  `supports_expression_indexes`; introspection reports an expression key
  without a column.

**Step D: unique variants** (#216)
- `lib_unique_catalog` ([approved in #213](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/213#issuecomment-6518630670)).
- `supports_nullable_unique_constraints`,
  `supports_partially_nullable_unique_constraints`; a conditional or functional
  `UniqueConstraint` is a `CREATE UNIQUE WHERE NOT NULL INDEX`.

**Step E: chunked reads and self-referencing statements** (#216)
- `can_use_chunked_reads`, `update_can_self_select`,
  `delete_can_self_reference_subquery`.

**Step B: conflicts through `MERGE`** (#216)
- Probe `qtemp_merge`; `supports_ignore_conflicts`, `supports_update_conflicts`,
  `supports_update_conflicts_with_target`. The compiler writes the `MERGE` with
  cast markers. `m2m.add()` goes through it, because Django uses
  `ignore_conflicts` for an auto-created many-to-many table.
- `MERGE` under concurrency: documented from IBM's documentation, marked not
  verified on IBM i, after the maintainer asked before the merge. Step B had left
  it out, although the plan's answer a required it.

**Close-out**
- This record, the four modules in `docs/status.toml`, and the flags and tracks
  below. The LOB tests were cut to just above the refused size, and their tables
  are created only in `test_inserts.py`.

## Key decisions
The answers of the plan's approval (2026-10-28):
[DECISIONS](../DECISIONS.md#2026-10-28-phase-5-plan-conflicts-last-with-an-exit-names-first).
- **Order:** step 0, names first (they affect many tests), then A, C, D, E, and
  conflicts last with an exit if `MERGE` proved unreliable. The exit was not
  needed.
- **`can_use_chunked_reads`:** the cursor probe decided, and it went on.
- **A2, B, C, D and E in one pull request** (maintainer, 2026-10-30): one IBM i
  cycle instead of five, with a commit per step.
- **The conflict flags stay on** while `MERGE` under concurrency is not verified
  (maintainer, 2026-10-31): [DECISIONS](../DECISIONS.md#2026-10-31-merge-under-concurrency-is-documented-its-verification-waits-for-a-dedicated-ibm-i).

**What moved elsewhere:**
- Off, with the reason in [features.toml](../features.toml):
  `supports_covering_indexes` (no `INCLUDE`), `can_return_rows_from_update`
  (`FINAL TABLE` takes only an `INSERT`),
  `supports_nulls_distinct_unique_constraints` (no such clause),
  `supports_deferrable_unique_constraints`,
  `allows_multiple_constraints_on_same_fields` (SQL0541).
- The verification of `MERGE` under concurrency: to a dedicated IBM i.
- No flag moved to phase 6 from this phase's plan.

## IBM i findings
Details and tables in IBMI_NOTES:
[step 0](../IBMI_NOTES.md#returning-bulk-inserts-indexes-unique-nulls-cursors-phase-5-step-0),
[step D](../IBMI_NOTES.md#unique-constraints-nulls-and-the-index-catalog-phase-5-step-d),
[step B](../IBMI_NOTES.md#merge-for-conflicts-in-bulk_create-phase-5-step-b),
[concurrency](../IBMI_NOTES.md#merge-under-concurrency-not-verified-on-ibm-i).
- `FINAL TABLE (INSERT ...)` returns identities and defaults, one row or many;
  `ORDER BY INPUT SEQUENCE` keeps the input order. `FINAL TABLE` takes no `UPDATE`
  or `MERGE` (SQL0199).
- A multi-row statement takes at most 32,767 markers and about 2 MB, but **only
  about 1,024 LOB markers** (1,056 got PWS0001 at prepare). `qtemp_bulk` used
  integers only; this limit came out when `bin/verify` ran
  `test_in_bulk_lots_of_ids`, and probe `qtemp_bulk_types` measured it. A `MERGE`
  has a limit too (refused at 1,100).
- A `UNIQUE` constraint treats NULLs as distinct, a plain unique index as equal;
  `UNIQUE WHERE NOT NULL` makes them distinct, also with a condition or expressions.
- `MERGE` needs typed markers (`CAST(? AS type)`, SQL0584 otherwise), and the same
  key twice in one source is refused (SQL0803 / SQL0788). A duplicate key met by its
  own insert undoes the whole statement under `*CS` (own IBM i test).

## Test status at the end of the phase
The phase's Django modules on PUB400 (IBM i 7.5), Python 3.14, one connection at
a time, `--clean`, 2026-10-31, on `4919cf7` (#216):

| Module | Django 6.1 | Django 6.0 | Django 5.2 | Baseline on 6.1 |
|---|---|---|---|---|
| `bulk_create` | 60 tests: 10 skipped, 7 expected failures | 59: 9 skipped, 7 expected failures | 52: 7 skipped, 7 expected failures | 16 passed, 43 skipped, 1 failed |
| `constraints` | 102: 15 skipped | 101: 14 skipped | 103: 14 skipped | 83 passed, 19 skipped |
| `indexes` | 31: 19 skipped, 1 expected failure | 31: 19 skipped, 1 expected failure | 31: 19 skipped, 1 expected failure | 6 passed, 24 skipped, 1 failed |
| `model_indexes` | 30: 2 skipped | 30: 2 skipped | 30: 2 skipped | 28 passed, 2 skipped |

0 failures and 0 errors in each. The expected failures have a fixed reason each
in `features.py`: `REASON_MERGE_RETURNS_NO_ROWS` (`instance.pk` after an upsert) and
`REASON_LOWERCASE_NAME_IN_SQL` (a test that searches the SQL for a lowercase name).
`basic`, `update` and `delete` passed in the same run. The own IBM i tests on 6.1:
373 passed, 1 expected failure (#216, `d373313`). The complete status of every
supported module and test set comes from the status run on `main` after this phase:
[TEST_STATUS](../TEST_STATUS.md).

## Carried forward
- **`lib_merge_concurrency`** (open track): two connections, so a dedicated IBM i,
  with its own approval. Known Limitations states expectations until then
  ([the cases](../IBMI_NOTES.md#merge-under-concurrency-not-verified-on-ibm-i)).
- **The LOB limit for 3 or more LOB columns** (open track): measured only for 1 and
  2; for 3 and 5, and for `MERGE`, the tests show that the batches work and which
  size is refused. Also not measured: the exact limit between 1,024 and 1,056, and
  where it starts between `NCLOB(1K)` and `NCLOB(1M)`.
- **The status run** after this phase, with the corpus rebuild: #216 removed 28
  replay entries per Django version that no run could stamp (24 plain many-to-many
  inserts, now `MERGE`; 3 with `datetime.now()` in their params; a 1998-row LOB
  insert). Until then the replay tests do not cover those `MERGE` statements and LOB
  batches; the Django tests do run them.
- **Limitations that stay** ([Known limitations](../user/Known-Limitations.md)):
  `update_conflicts` sets no keys on the objects, 7 expected failures per version (a
  second query could read them back; not planned); the same key twice in one call
  raises `IntegrityError`; conditional or functional unique constraints are not
  matched.
- **Phase 6**: the flags with `planned = "phase 6"` in
  [FEATURES](../FEATURES.md), among them window functions, `JSONField`, DB-level
  `on_delete`, `select_for_update` and, after a probe,
  `supports_no_precision_decimalfield`.
- **Open issues:** [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82)
  (`annotations` / `expressions_case`), [#95](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/95)
  (`Value(Decimal(...))`), [#124](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/124)
  (tables in another library than `NAME`).

## Links
- [DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md), [FEATURES.md](../FEATURES.md),
  [TEST_STATUS.md](../TEST_STATUS.md), [Known limitations](../user/Known-Limitations.md).
- Changelog: the fragments in `changelog.d/` until the next release.
- The approved plan: this file from the merge of #208 until this close-out.
