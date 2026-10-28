# Phase 5: Returning & bulk

> Status: Proposed, not yet approved

## Goal
From CLAUDE.md section 9: **returning & bulk**: `FINAL TABLE` returning
columns, `bulk_create`, unique constraint variants, partial / expression /
covering indexes; the `constraints`, `indexes` and `model_indexes` modules
(the phase 4/5 boundary: [DECISIONS](../DECISIONS.md#2026-10-21-phase-4-and-phase-5-schema-needs-first-constraint-and-index-variants-later)).

Proposed "done when":
- **The Django modules `bulk_create`, `constraints`, `indexes` and
  `model_indexes` run on 6.1, 6.0 and 5.2 against PUB400 without failures
  or errors**: every remaining failure is a skip or expected failure with one
  fixed reason, and the four modules join the supported modules
  (`docs/status.toml`, the status run).
- **Every flag `planned = "phase 5"`** in [features.toml](../features.toml)
  is on where the tests back it, or off with a reason (no "phase 5" left);
  each flag that is turned on comes with its own IBM i test of the
  real-world pattern (CLAUDE.md section 2).
- **Goldens** for every new SQL shape (returning insert, multi-row insert,
  index and constraint variants), per Django series, all verified on PUB400.
- **The probe results** a decision rests on are in IBMI_NOTES and
  `probes/results/`.

## 1. Where the backend stands
- **Inserts** are single-row `INSERT ... VALUES`. The primary key comes from
  a second statement, `SELECT IDENTITY_VAL_LOCAL() FROM SYSIBM.SYSDUMMY1`
  (`operations.last_insert_id()`), which is only reliable after a single-row
  insert ([DECISIONS](../DECISIONS.md#2026-10-17-last_insert_id-via-identity_val_local)).
  `has_bulk_insert` is off, so `bulk_create()` sends one `INSERT` per object,
  and `can_return_rows_from_bulk_insert` is off, so the created objects get no
  primary keys.
- **`db_default`**: inserts leave the column out instead of writing `DEFAULT`
  (`supports_default_keyword_in_insert` off).
- **Indexes**: plain, unique and ordered indexes (`supports_index_column_ordering`),
  `RENAME INDEX`; no `condition`, expressions or `include`.
- **Constraints**: unique, check and foreign key constraints, with full
  introspection (phase 4). A second unique constraint on the same columns
  fails with SQL0541 ([IBMI_NOTES](../IBMI_NOTES.md#foreign-keys-unique-and-check-constraints-nox--s-probe_constraints----execute)),
  so `allows_multiple_constraints_on_same_fields` is off. Nothing is
  deferrable.
- **Names**: `quote_name()` already shortens names longer than 128 with
  Django's `truncate_name()`; `truncates_names` is still off.
- **Identity restarts**: `sequence_reset_sql` exists (`RESTART WITH`,
  verified), `supports_sequence_reset` is off.

## 2. Django test modules
Tests per module (`def test_` in `vendor/django-<version>/tests/<module>`):

| Module | 5.2 | 6.0 | 6.1 | Status today |
|---|---|---|---|---|
| `bulk_create` | 52 | 59 | 60 | not run on IBM i |
| `constraints` | 103 | 101 | 102 | not run on IBM i |
| `indexes` | 31 | 31 | 31 | not run on IBM i |
| `model_indexes` | 30 | 30 | 30 | not run on IBM i |

Step 0 runs each module once on 6.1 (with `--clean`), so the plan starts
from real numbers: how many pass with today's flags, and which fail for
which reason. Related tests in modules that are already supported (`schema`,
`migrations`, `introspection`) that are skipped today because a phase 5 flag
is off come back when the flag is turned on; the status run shows them.

## 3. Feature flags phase 5 touches
The 24 flags with `planned = "phase 5"` (#198 included `truncates_names` and
`supports_sequence_reset`). Expected outcome per flag, to be settled by the
probes in section 4; "(not verified on IBM i)" marks an expectation that
rests on Db2 for i documentation only.

| Group | Flag | Expectation |
|---|---|---|
| Returning | `can_return_columns_from_insert` | on: `SELECT ... FROM FINAL TABLE (INSERT ...)` |
| | `can_return_rows_from_bulk_insert` | on if a multi-row `FINAL TABLE` insert returns rows in input order (`ORDER BY INPUT SEQUENCE`, not verified on IBM i) |
| | `can_return_rows_from_update` (6.0+) | on if `FINAL TABLE (UPDATE ...)` works (not verified on IBM i) |
| Bulk | `has_bulk_insert` | on: multi-row `VALUES (...), (...)`, with a batch size from the statement and parameter limits |
| | `supports_default_keyword_in_insert`, `supports_default_keyword_in_bulk_insert` | on if `DEFAULT` is accepted in `VALUES` (not verified on IBM i) |
| | `allows_auto_pk_0` | depends on whether an identity column takes an explicit 0 |
| | `supports_ignore_conflicts`, `supports_update_conflicts`, `supports_update_conflicts_with_target` | Db2 for i has no `ON CONFLICT`; `MERGE` could emulate them (open question 1) |
| Indexes | `supports_partial_indexes`, `supports_functions_in_partial_indexes` | on if `CREATE INDEX ... WHERE` works (not verified on IBM i) |
| | `supports_expression_indexes` | on if indexes on expressions work (not verified on IBM i) |
| | `supports_covering_indexes` | expected off: no `INCLUDE` known on Db2 for i (probe confirms) |
| Unique | `supports_nullable_unique_constraints`, `supports_partially_nullable_unique_constraints` | depends on how a unique constraint treats NULLs (probe) |
| | `supports_nulls_distinct_unique_constraints` | depends on the same probe; Django needs both `NULLS DISTINCT` and `NOT DISTINCT` |
| | `supports_deferrable_unique_constraints` | expected off: nothing is deferrable on Db2 for i |
| | `allows_multiple_constraints_on_same_fields` | expected off (SQL0541, already probed); stays off with that reason |
| Names, misc | `truncates_names` | on: `quote_name()` already truncates (#198) |
| | `supports_sequence_reset` | on: `RESTART WITH` is verified; `sqlsequencereset` needs `MAX()` first |
| | `can_use_chunked_reads` | depends on whether pyodbc keeps an open cursor usable while other statements run on the same connection (probe) |
| | `delete_can_self_reference_subquery`, `update_can_self_select` | on if Db2 for i accepts a subquery on the target table (probe) |

## 4. IBM i questions and probes
All of these can run in QTEMP (read-only plus QTEMP tables, commitment
control off for the session as in `qtemp_later_flags`), so they need no
approval. One probe per topic, each published with `bin/probe --publish`:

| Probe | Questions |
|---|---|
| `qtemp_returning` | `FINAL TABLE (INSERT ...)` single and multi-row; `ORDER BY INPUT SEQUENCE`; returned identity and `db_default` values; `FINAL TABLE (UPDATE ...)`; `DEFAULT` in `VALUES`; an explicit 0 in an identity column |
| `qtemp_bulk` | the largest multi-row insert: rows, parameter markers and statement length before an error, and the SQLCODE (for `bulk_batch_size()`); `MERGE` for ignore / update conflicts |
| `qtemp_indexes` | `CREATE INDEX ... WHERE` (with functions), indexes on expressions, `INCLUDE`, unique indexes with a condition; how `QSYS2.SYSINDEXES` / `SYSKEYS` show each (for introspection) |
| `qtemp_unique_nulls` | a unique constraint and a unique index on nullable columns: one or several NULLs, `NULLS DISTINCT` / `NOT DISTINCT`, partially NULL multi-column keys |
| `qtemp_cursors` | two open cursors on one connection, one fetching while the other writes (chunked reads); a `DELETE` / `UPDATE` with a subquery on the same table |

**One risk:** QTEMP refused constraints in probe 22 (SQL7008). If
`qtemp_unique_nulls` cannot create a unique *constraint* in QTEMP even with
commitment control off, that question needs a `lib_` probe in the journaled
test library, which needs your approval as a GitHub comment. I would open
that request then, with exactly what it creates and how it cleans up.

## 5. Design
- **Returning:** `return_insert_columns()` and the insert compiler write
  `SELECT <columns> FROM FINAL TABLE (INSERT INTO ... VALUES ...)`; the
  returned row replaces `IDENTITY_VAL_LOCAL()`. The driver layer stays as it
  is: the statement is a query that returns rows. `last_insert_id()` stays as
  the fallback for anything that does not use returning.
- **Bulk insert:** multi-row `VALUES` with `bulk_batch_size()` from the
  probe's limits; with returning, `ORDER BY INPUT SEQUENCE` if the probe
  confirms it, otherwise `can_return_rows_from_bulk_insert` stays off.
- **Conflicts:** only if open question 1 says so: `MERGE INTO <table> USING
  (VALUES ...) ON <unique columns> WHEN NOT MATCHED THEN INSERT [WHEN MATCHED
  THEN UPDATE]`.
- **Indexes and unique variants:** in `schema.py` through Django's existing
  hooks (`_create_index_sql`, `_create_unique_sql`, the `condition`,
  `expressions` and `include` arguments); introspection reports what the
  probe shows in the catalog, so `get_constraints()` stays complete.
- **Capabilities:** a feature that depends on the IBM i release or a PTF
  level gets a capability (CLAUDE.md section 4), so 7.4 can be added later
  without touching this code.

## 6. Test strategy
- **Offline:** goldens for each new SQL shape per Django series; unit tests
  for `bulk_batch_size()` and the returning SQL.
- **IBM i tests:** per enabled flag, the common pattern: `create()` reading
  back the key and a `db_default`; `bulk_create()` of a few hundred objects
  with keys set; a partial and an expression index used by a migration; a
  nullable unique field with several NULLs.
- **Django modules:** targeted runs per PR of the module the flag affects;
  each flag's PR updates the skips and expected failures with one fixed
  reason per entry.
- **IBM i runs:** most PRs touch `operations.py`, `schema.py`,
  `introspection.py`, `compiler.py` or `features.py` (core backend), so each
  gets the full IBM i tests on 6.1 (#199).

## 7. Plan with PR boundaries
| Step | PRs | Content |
|---|---|---|
| 0 | 1 | the five QTEMP probes, IBMI_NOTES, a baseline run of the four modules on 6.1; `features.toml` updated from the results |
| A | 2–3 | returning: `can_return_columns_from_insert` (+ `DEFAULT`, `allows_auto_pk_0` if the probe allows); then `has_bulk_insert` + `can_return_rows_from_bulk_insert`; the `bulk_create` module |
| B | 0–2 | conflicts through `MERGE`, if open question 1 says so |
| C | 2 | indexes: partial (+ functions) and expression indexes, `include` if supported; the `indexes` and `model_indexes` modules |
| D | 1–2 | unique variants: nullable, partially nullable, `nulls_distinct`; the `constraints` module |
| E | 1–2 | `truncates_names`, `supports_sequence_reset`, `can_use_chunked_reads`, the self-referencing `UPDATE` / `DELETE`, `can_return_rows_from_update` |
| Close-out | 2 | the four modules into `docs/status.toml`, a status run on 5.2 / 6.0 / 6.1, TEST_STATUS, this file rewritten as the record |

About 10 to 14 PRs. Steps A, C and D are independent after step 0 and can
run in parallel worktrees; IBM i runs stay one at a time.

## Key decisions
None yet; the answers to the open questions go here and into DECISIONS.

## IBM i findings
None yet; the probe results of step 0 go here.

## Test status at the end of the phase
Not started.

## Carried forward
Not started. Already known for later phases: JSONField, window functions,
DB-level `on_delete` and the flags #198 assigned to phase 6.

## Links
- [features.toml](../features.toml): the flags `planned = "phase 5"`
- [DECISIONS](../DECISIONS.md#2026-10-21-phase-4-and-phase-5-schema-needs-first-constraint-and-index-variants-later): the phase 4/5 boundary
- [phase-4.md](phase-4.md): "Carried forward"

## Open questions
1. **Conflicts (`ignore_conflicts`, `update_conflicts`) through `MERGE`:** in
   phase 5 (step B), or later? `MERGE` is a different statement than Django
   expects for an insert, and its result does not map one-to-one to
   "returned rows"; skipping it keeps three flags off with a reason.
2. **The four modules as supported modules:** about 220 more tests per Django
   version in every status run (now about 2 hours per version). Agreed?
3. **A `lib_` probe for unique constraints** if QTEMP refuses them (section
   4): I'd open the approval request then. Agreed in principle?
4. **`can_use_chunked_reads`:** worth it on a shared system with one
   connection? If the probe shows any risk to the connection, I propose to
   keep it off with that reason.
5. **The order of steps A, C and D**, or one of them first: is there a
   feature you need sooner?
6. **`truncates_names` and `supports_sequence_reset`** are small and already
   verified: first, in step 0's PR, or in step E as planned?
