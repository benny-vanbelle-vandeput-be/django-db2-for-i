# Phase 5: Returning & bulk

> Status: Approved, 2026-10-28. Implementation starts after the beta tag
> (`v0.1.0b1`); see "Before the beta".

## Goal
From CLAUDE.md section 9: **returning & bulk**: `FINAL TABLE` returning
columns, `bulk_create`, unique constraint variants, partial / expression /
covering indexes; the `constraints`, `indexes` and `model_indexes` modules
(the phase 4/5 boundary: [DECISIONS](../DECISIONS.md#2026-10-21-phase-4-and-phase-5-schema-needs-first-constraint-and-index-variants-later)).

"Done when" (approved, answer b):
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

| Module | 5.2 | 6.0 | 6.1 | Baseline on 6.1 (step 0) |
|---|---|---|---|---|
| `bulk_create` | 52 | 59 | 60 | 16 passed, 43 skipped, 1 failed |
| `constraints` | 103 | 101 | 102 | 83 passed, 19 skipped |
| `indexes` | 31 | 31 | 31 | 6 passed, 24 skipped, 1 failed |
| `model_indexes` | 30 | 30 | 30 | 28 passed, 2 skipped |

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
| | `supports_ignore_conflicts`, `supports_update_conflicts`, `supports_update_conflicts_with_target` | Db2 for i has no `ON CONFLICT`; emulated with `MERGE` in step B, the last step (answer a), or moved to later with the probe result as reason |
| Indexes | `supports_partial_indexes`, `supports_functions_in_partial_indexes` | on if `CREATE INDEX ... WHERE` works (not verified on IBM i) |
| | `supports_expression_indexes` | on if indexes on expressions work (not verified on IBM i) |
| | `supports_covering_indexes` | expected off: no `INCLUDE` known on Db2 for i (probe confirms) |
| Unique | `supports_nullable_unique_constraints`, `supports_partially_nullable_unique_constraints` | depends on how a unique constraint treats NULLs (probe) |
| | `supports_nulls_distinct_unique_constraints` | depends on the same probe; Django needs both `NULLS DISTINCT` and `NOT DISTINCT` |
| | `supports_deferrable_unique_constraints` | expected off: nothing is deferrable on Db2 for i |
| | `allows_multiple_constraints_on_same_fields` | expected off (SQL0541, already probed); stays off with that reason |
| Names, misc | `truncates_names` | on: `quote_name()` already truncates (#198) |
| | `supports_sequence_reset` | on: `RESTART WITH` is verified; `sqlsequencereset` needs `MAX()` first |
| | `can_use_chunked_reads` | the cursor probe decides (answer d): on in step E if it works without workarounds, otherwise moved to phase 6 |
| | `delete_can_self_reference_subquery`, `update_can_self_select` | on if Db2 for i accepts a subquery on the target table (probe) |

## 4. IBM i questions and probes
All of these can run in QTEMP (read-only plus QTEMP tables, commitment
control off for the session as in `qtemp_later_flags`), so they need no
approval. One probe per topic, each published with `bin/probe --publish`:

| Probe | Questions |
|---|---|
| `qtemp_returning` | `FINAL TABLE (INSERT ...)` single and multi-row; `ORDER BY INPUT SEQUENCE`; returned identity and `db_default` values; `FINAL TABLE (UPDATE ...)`; `DEFAULT` in `VALUES`; an explicit 0 in an identity column |
| `qtemp_bulk` | the largest multi-row insert: rows, parameter markers and statement length before an error, and the SQLCODE (for `bulk_batch_size()`) |
| `qtemp_merge` | step B, first: `MERGE` for ignore / update conflicts, its row counts, and what a concurrent insert of the same key does (answer a) |
| `qtemp_indexes` | `CREATE INDEX ... WHERE` (with functions), indexes on expressions, `INCLUDE`, unique indexes with a condition; how `QSYS2.SYSINDEXES` / `SYSKEYS` show each (for introspection) |
| `qtemp_unique_nulls` | a unique constraint and a unique index on nullable columns: one or several NULLs, `NULLS DISTINCT` / `NOT DISTINCT`, partially NULL multi-column keys |
| `qtemp_cursors` | two open cursors on one connection, one fetching while the other writes (chunked reads); a `DELETE` / `UPDATE` with a subquery on the same table |

**One risk:** QTEMP refused constraints in probe 22 (SQL7008). If
`qtemp_unique_nulls` cannot create a unique *constraint* in QTEMP even with
commitment control off, that question needs a `lib_` probe in the journaled
test library. Agreed in principle (answer c), but the normal rule applies:
each `lib_` probe is requested separately, saying what it creates and how it
cleans up, and runs only after the maintainer's approval comment on GitHub
(`bin/probe --approved <link>`).

**Concurrency of `MERGE`** (answer a): `MERGE` is not race-free. Two jobs
that insert the same new key at the same time can both find no match, and
one of them still gets a duplicate-key error (SQL0803). Step B investigates
and documents what Db2 for i does there (one connection on PUB400 cannot
run two jobs at once, so the probe covers what a single job can show, and
the rest is documented as a limitation), and maps the error to
`IntegrityError` as for a plain insert.

## 5. Design
- **Returning:** `return_insert_columns()` and the insert compiler write
  `SELECT <columns> FROM FINAL TABLE (INSERT INTO ... VALUES ...)`; the
  returned row replaces `IDENTITY_VAL_LOCAL()`. The driver layer stays as it
  is: the statement is a query that returns rows. `last_insert_id()` stays as
  the fallback for anything that does not use returning.
- **Bulk insert:** multi-row `VALUES` with `bulk_batch_size()` from the
  probe's limits; with returning, `ORDER BY INPUT SEQUENCE` if the probe
  confirms it, otherwise `can_return_rows_from_bulk_insert` stays off.
- **Conflicts (step B, the last step):** `MERGE INTO <table> USING
  (VALUES ...) ON <unique columns> WHEN NOT MATCHED THEN INSERT [WHEN MATCHED
  THEN UPDATE]`. **Exit:** if the `qtemp_merge` probe shows `MERGE` is not
  reliable for this (wrong row counts, refused shapes, or behaviour Django's
  tests cannot accept), the three conflict flags move to a later phase with
  the probe result as the reason, and phase 5 is done without them.
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
  gets the full IBM i tests on 6.1 (#199). Step A changes the compiler, so
  each of its PRs gets the full run: about 15 to 20 minutes on PUB400 per
  PR, plus a new one after every rebase over a run-requiring commit.

## 7. Plan with PR boundaries
In this order (answers e and f):

| Step | PRs | Content |
|---|---|---|
| 0 | 1 | the QTEMP probes of section 4 (except `qtemp_merge`), IBMI_NOTES, `features.toml` updated from the results; a baseline run of the four modules on 6.1 after the beta tag |
| Names | 1 | `truncates_names` and `supports_sequence_reset`, right after the baseline: `truncates_names` affects many tests, so later measurements are cleaner |
| A | 2–3 | returning: `can_return_columns_from_insert` (+ `DEFAULT`, `allows_auto_pk_0` if the probe allows); then `has_bulk_insert` + `can_return_rows_from_bulk_insert`; the `bulk_create` module. Full IBM i run per PR (compiler) |
| C | 2 | indexes: partial (+ functions) and expression indexes, `include` if supported; the `indexes` and `model_indexes` modules |
| D | 1–2 | unique variants: nullable, partially nullable, `nulls_distinct`; the `constraints` module |
| E | 1–2 | `can_use_chunked_reads` (if the probe allows), the self-referencing `UPDATE` / `DELETE`, `can_return_rows_from_update` |
| B | 2–3 | conflicts, last: the `qtemp_merge` probe, then `ignore_conflicts`, then `update_conflicts`; or the exit in section 5 |
| Close-out | 2 | the four modules into `docs/status.toml`, a status run on 5.2 / 6.0 / 6.1, TEST_STATUS, this file rewritten as the record |

About 12 to 16 PRs. IBM i runs stay one at a time.

**Changed 2026-10-30 (maintainer):** A2, B, C, D and E go into one pull
request (#216), with a commit per step, to save PUB400 time: one IBM i cycle
for all of them (the full IBM i tests on 6.1, `bin/verify` per Django
version, the affected modules on 6.1, 6.0 and 5.2) instead of five. While
building, only small targeted runs. D came in after the approval of the
`lib_` probe (#213), B after the `qtemp_merge` probe; the close-out stays a
separate pull request.

## Before the beta
Until the tag `v0.1.0b1` exists (checked read-only with
`git ls-remote --tags origin`; the maintainer sets it):
- **No implementation** commits on branches meant for `main`, and no
  implementation PRs.
- **Allowed as preparation**, in a local worktree that is not pushed: the
  probe scripts, offline tests, draft goldens (marked unverified), notes for
  IBMI_NOTES, the expected-failure analysis. After the tag: rebase on
  `main`, then open the PRs in the order above.
- **PUB400:** the IBM i runs of the pre-beta pause PRs come first, then the
  status run for the beta, then phase 5. The QTEMP probes may run before the
  beta, but only when PUB400 is free (never during a status run or another
  PR's IBM i run), with one connection and the lock, and no retries when
  PUB400 is unreachable: try again later. The baseline run of the four
  modules waits until after the tag, so it measures the code phase 5 builds
  on.

## Key decisions
The answers of the plan's approval (2026-10-28), also in
[DECISIONS](../DECISIONS.md#2026-10-28-phase-5-plan-conflicts-last-with-an-exit-names-first):
- **a. Conflicts through `MERGE`:** in phase 5, as the last step: the
  `MERGE` probe, then `ignore_conflicts`, then `update_conflicts`.
  Concurrent inserts are investigated and documented (`MERGE` is not
  race-free). Exit: if `MERGE` is unreliable, the conflict flags move to
  later with the probe result as the reason.
- **b. Supported modules:** `bulk_create`, `constraints`, `indexes` and
  `model_indexes` become supported modules; that is the "done when".
- **c. `lib_` probe for unique constraints:** yes in principle, if QTEMP
  refuses them; each `lib_` probe is still requested separately and waits
  for the maintainer's approval on GitHub.
- **d. `can_use_chunked_reads`:** not a priority. The cursor probe decides:
  on in step E if it works without workarounds, otherwise phase 6.
- **e. Order:** step 0, then `truncates_names` and
  `supports_sequence_reset`, then A, C, D, E, B, close-out.
- **f. Names first:** `truncates_names` and `supports_sequence_reset` right
  after the baseline, because `truncates_names` affects many tests.

## IBM i findings
**Baseline** (step 0, 2026-10-29): the four modules once on 6.1 with
`--clean`, on `main` at the beta tag (`v0.1.0b1`, `dd7f255`); logs kept in
`test-results/phase5-baseline/`. Numbers in section 2. Two failures:
- `bulk_create.tests.BulkCreateTests.test_zero_as_autoval`: with
  `allows_auto_pk_0` off Django expects a `ValueError` for a 0 key, which only
  MySQL's backend raises. Db2 for i takes a 0 (probe below), so the flag goes
  on in step A and the test is skipped by the flag.
- `indexes.tests.PartialIndexConditionIgnoredTests.test_condition_ignored`:
  with `supports_partial_indexes` off, the backend still writes the `WHERE`
  of an `Index(condition=...)`: it inherits Django's `sql_create_index` with
  `%(condition)s` (MySQL and Oracle have their own without it). Step C turns
  the flag on, which settles it.

**Probes** (step 0, 2026-10-29, QTEMP only; details and tables in
[IBMI_NOTES](../IBMI_NOTES.md#returning-bulk-inserts-indexes-unique-nulls-cursors-phase-5-step-0)):
- `qtemp_returning`: `FINAL TABLE (INSERT ...)` returns the identity and the
  defaults, one row and many; `ORDER BY INPUT SEQUENCE` keeps the input order
  (200 rows, explicit keys mixed in). `DEFAULT` in `VALUES` works, also
  multi-row; an explicit 0 in an identity column works. `FINAL TABLE (UPDATE
  ...)` is refused (SQL0199): `can_return_rows_from_update` is off.
- `qtemp_bulk`: at most 32,767 parameter markers (32,640 worked, 32,768 got
  SQL0901, a system error); statements up to about 2 MB; at most about
  32,700 rows. `bulk_batch_size()` stays well below.
- `qtemp_indexes`: partial indexes (with functions), expression indexes
  and unique variants of both work; `INCLUDE` does not (SQL0104):
  `supports_covering_indexes` is off.
- `qtemp_unique_nulls`: a plain unique index treats NULLs as equal; `UNIQUE
  WHERE NOT NULL` and a unique index `WHERE <column> IS NOT NULL` allow
  several NULLs; no `NULLS [NOT] DISTINCT` (SQL0199):
  `supports_nulls_distinct_unique_constraints` is off. Unique *constraints*
  cannot be made in QTEMP (SQL7008): that question waits for a `lib_` probe.
- `qtemp_cursors`: chunked fetches on one cursor while a second one reads
  and writes; `DELETE` / `UPDATE` with a subquery on the same table: all
  work (without commitment control; step E checks it with Django's tests).

Off after step 0, with the reason in `features.toml`:
`supports_covering_indexes`, `can_return_rows_from_update`,
`supports_nulls_distinct_unique_constraints`,
`supports_deferrable_unique_constraints`,
`allows_multiple_constraints_on_same_fields`.

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
All answered at approval (see "Key decisions").
