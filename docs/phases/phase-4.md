# Phase 4: Schema editor completeness

> Status: Done (2026-10-27)

## Goal
From CLAUDE.md section 9: **schema editor completeness**: `schema`,
`migrations`, `introspection`, `inspectdb`, and what they need: foreign keys,
check constraints, introspection of every constraint, index ordering and
text-field indexes. Also: verify the column order of created tables
([#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23)).
Step 0 (tooling) was added to the phase before the schema work (decision 11
of the plan).

"Done when" (approved plan, 2026-10-21), and how it was met:
- **Step 0 done**: the rules for IBM i runs are in CLAUDE.md and
  CONTRIBUTING.md, the classification and the IBM i gate run in CI, every
  `bin/` script exists with offline tests, `docs/WORKFLOW.md` documents them.
- **The Django modules `introspection`, `inspectdb`, `schema` and
  `migrations` run on 6.1, 6.0 and 5.2 against PUB400 without failures or
  errors**: every remaining failure is a skip or expected failure with one
  fixed reason ([#152](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/152),
  [#177](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/177),
  [#184](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/184),
  [#186](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/186)).
  `migrations` runs as the whole module, not as the five labels the plan
  named (decision 6). Of the two smaller modules in decision 6,
  `migrate_signals` passes on every version and is supported;
  `migration_test_data_persistence` is not (see "Carried forward").
- **The phase 4 flags are on where the tests back them**, each with its own
  IBM i test of the real-world pattern (see "What was done").
- **DDL goldens** exist for every migration operation the backend supports,
  per Django series, all verified on PUB400 (the verification gate passes
  with no unverified golden).
- **Issue #23** is answered (offline golden, own IBM i test, user docs) and
  the foreign key part of [#96](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/96)
  is done.
- **The CPA32B2 / table rebuild question** has recorded decisions: CPA32B2
  is suppressed per job in migrations, and there is no table rebuild.

The approved plan, with its analysis of the Django modules, the flags and
the design, is in this file's history (from the merge of
[#123](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/123),
with its progress updates, until #187 replaced it with this record).

## What was done

**Step 0: tooling**
- IBM i runs follow an automatic classification of every PR
  (`scripts/classify_pr.py`, labels `needs-full-tier` / `run-ibmi`, one PR
  comment). [#126](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/126), [#139](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/139), [#159](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/159)
- The verification gate (`nox -s gate`) with a shared allow-list, and the
  status run set. [#127](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/127)
- The PUB400 lock (one job at a time on a machine), `bin/check`,
  `bin/status`, `bin/doctor`, `bin/probe`, `bin/ibmi-test`,
  `bin/ibmi-cleanup` with the cleanup list, `bin/verify`, `bin/setup`,
  `bin/release-run`, `bin/release-prepare`, `bin/worktree-remove`,
  `docs/WORKFLOW.md` and `bin/help`. [#128](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/128), [#129](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/129), [#130](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/130), [#131](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/131), [#132](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/132), [#133](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/133), [#137](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/137)
- Probe names say where a probe acts (`qtemp_` / `lib_`), and a `lib_` probe
  needs the maintainer's approval comment on GitHub. [#143](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/143)
- The IBM i gate (`ibmi-gate`), a required commit status independent of the
  labels. [#161](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/161), [#166](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/166)
- The PUB400 lock stops the run's container and handles signals.
  [#167](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/167), [#169](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/169)

**Step A: facts first**
- Probe 24 (`alter_table`), probe 25 (`catalog`) and the baseline runs of
  `introspection` and `schema`. [#134](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/134)
- Write probe w13 (constraints) in the journaled `default` library.
  [#135](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/135)
- The column order of created tables is the model's field order (#23).
  [#136](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/136)

**Step B: introspection**
- `get_constraints()` from the QSYS2 catalog; `get_relations()` with
  `can_introspect_foreign_keys`; field types, lengths and defaults from the
  catalog (write probe w14). [#138](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/138), [#140](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/140), [#141](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/141), [#144](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/144)
- One trailing semicolon is removed from every statement; Django's own
  `DEFAULT_AUTO_FIELD` per version in the IBM i test settings.
  [#142](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/142), [#145](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/145)

**Step C: schema editor**
- `ALTER COLUMN ... SET DATA TYPE`; `RENAME TABLE`, `RENAME INDEX`
  (`can_rename_index`) and identity changes; renamed test tables stay on the
  cleanup list. [#146](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/146), [#147](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/147), [#148](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/148)
- Expected failures for column renames and type changes Db2 for i cannot
  make in place; those type changes are refused before any SQL (SQL0190).
  [#152](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/152), [#177](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/177)
- Check constraints (`supports_column_check_constraints`,
  `supports_table_check_constraints`); a system check for journaled
  libraries. [#155](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/155), [#157](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/157)
- `can_rollback_ddl`: a migration runs in one transaction and a failure
  rolls it back, also when a deferred statement fails (`lib_rollback_ddl`).
  [#153](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/153), [#158](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/158), [#160](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/160), [#179](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/179)
- Foreign keys (`supports_foreign_keys`, `indexes_foreign_keys`):
  violations as `IntegrityError`, foreign key DDL goldens, the facts of the
  schema editor's foreign key handling. [#163](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/163), [#168](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/168), [#170](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/170)
- A `NOT NULL` column without a default (SQL0109). [#164](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/164)
- CPA32B2 suppressed per job in migrations (`OVERRIDE_QAQQINI`), with
  `inquiry_message_reply` as the fallback; narrowing changes refused when a
  value would change; SQL0910 in migrations documented.
  [#171](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/171), [#172](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/172), [#174](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/174), [#175](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/175), [#180](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/180)
- Indexes: `db_index` on a LOB column is skipped;
  `supports_index_column_ordering`. [#176](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/176), [#178](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/178)
- Decisions without code: no table rebuild; `supports_comments` stays off.
  [#181](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/181), [#182](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/182)
- A literal `%` in column defaults; the per-version expected failures of
  `migrations`. [#183](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/183), [#184](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/184)

**Step D: inspectdb**
- `supports_inspectdb` and `ignores_table_name_case`; `NUMERIC` and `CLOB`
  introspected; an own IBM i test of `inspectdb` on tables created with
  plain SQL. [#186](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/186)

**Close-out**
- This record; the user docs; `docs/status.toml` (`migrate_signals` added
  to the supported modules, phase 4 done, two stale tracks removed); the
  phase 4 feature flags decided or carried forward in
  `docs/features.toml`. [#187](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/187)

## Key decisions
- Phase 4 is what the schema modules need; constraint and index variants
  are phase 5: [DECISIONS](../DECISIONS.md#2026-10-21-phase-4-and-phase-5-schema-needs-first-constraint-and-index-variants-later)
- CPA32B2: the affected tests as expected failures first, then suppressed
  per job in migrations, with the job's reply setting as the fallback: [DECISIONS](../DECISIONS.md#2026-10-21-cpa32b2-in-phase-4-opt-in-reply-list-affected-tests-as-expected-failures), [DECISIONS](../DECISIONS.md#2026-10-25-cpa32b2-suppressed-per-job-in-migrations), [DECISIONS](../DECISIONS.md#2026-10-26-inquiry_message_reply-stays-as-the-fallback)
- No table rebuild for column renames and incompatible type changes: [DECISIONS](../DECISIONS.md#2026-10-26-no-table-rebuild-for-column-renames-and-incompatible-type-changes)
- Foreign keys as separate statements, Django's own index kept: [DECISIONS](../DECISIONS.md#2026-10-21-foreign-keys-separate-statements-own-index-kept)
- `supports_comments` stays off: [DECISIONS](../DECISIONS.md#2026-10-21-supports_comments-only-if-unicode-text-works), [DECISIONS](../DECISIONS.md#2026-10-26-supports_comments-stays-off)
- `db_index` on a `TextField` or `BinaryField` is skipped: [DECISIONS](../DECISIONS.md#2026-10-26-db_index-on-a-textfield-or-binaryfield-is-skipped)
- The first per-version expected-failure list: [DECISIONS](../DECISIONS.md#2026-10-24-the-first-per-version-expected-failure-list)
- Probe w13 in the journaled `default` library: [DECISIONS](../DECISIONS.md#2026-10-21-probe-w13-in-the-journaled-default-library)
- Tooling: [the PR classification](../DECISIONS.md#2026-10-21-ibm-i-runs-follow-an-automatic-pull-request-classification),
  [the verification gate](../DECISIONS.md#2026-10-21-the-verification-gate-is-its-own-nox-session-with-a-shared-allow-list),
  [bin/ scripts and the PUB400 lock](../DECISIONS.md#2026-10-21-bin-scripts-in-bash-32-the-pub400-lock-in-the-hosts-python),
  [the cleanup list](../DECISIONS.md#2026-10-21-the-cleanup-list-is-written-by-the-test-settings-next-to-the-pub400-lock),
  [the marker per pub400 module](../DECISIONS.md#2026-10-22-every-pub400-module-that-creates-testapp-tables-owns-the-marker),
  [bin/verify](../DECISIONS.md#2026-10-22-binverify-runs-exactly-what-needs-ibm-i-within-fixed-limits),
  [the release scripts](../DECISIONS.md#2026-10-22-release-scripts-a-resumable-release-run-and-a-release-pr-that-never-tags)

## IBM i findings
Details in [IBMI_NOTES.md](../IBMI_NOTES.md):
- `ALTER TABLE` forms, renames, indexes and the row length (probe 24): [IBMI_NOTES](../IBMI_NOTES.md#alter-table-renames-indexes-and-row-length-probe----alter_table)
- The catalog views introspection reads; QTEMP objects are not in them
  (probe 25): [IBMI_NOTES](../IBMI_NOTES.md#catalog-views-for-introspection-probe----catalog)
- Constraints in the catalog (w13) and column types in the catalog (w14): [IBMI_NOTES](../IBMI_NOTES.md#foreign-keys-unique-and-check-constraints-nox--s-probe_constraints------execute), [IBMI_NOTES](../IBMI_NOTES.md#column-types-in-the-catalog-nox--s-probe_column_types------execute)
- `ALTER COLUMN` on indexed, unique and identity columns; no statement
  renames a column; which type changes work in place: [IBMI_NOTES](../IBMI_NOTES.md#alter-column-on-indexed-unique-and-identity-columns-probe----alter_column), [IBMI_NOTES](../IBMI_NOTES.md#column-renames-and-identity-changes-probe----renames), [IBMI_NOTES](../IBMI_NOTES.md#column-type-changes-in-place-probe----type_changes)
- CHECK constraints on a table that is not journaled, and CHECK with LIKE
  against a column pattern (SQL0546): [IBMI_NOTES](../IBMI_NOTES.md#check-constraints-on-a-table-that-is-not-journaled-probe----check_journal), [IBMI_NOTES](../IBMI_NOTES.md#check-with-like-against-a-column-pattern-sql0546-django-migrations)
- What a `ROLLBACK` undoes of DDL, and that no statement starts a
  transaction: [IBMI_NOTES](../IBMI_NOTES.md#ddl-under-commitment-control-what-rollback-undoes-lib_rollback_ddl), [IBMI_NOTES](../IBMI_NOTES.md#no-statement-starts-a-transaction-probe----transaction_start)
- Foreign keys through the schema editor (facts a-d): [IBMI_NOTES](../IBMI_NOTES.md#foreign-keys-through-the-schema-editor-own-ibm-i-tests-facts-a-d)
- `ADD COLUMN ... NOT NULL` without a default: [IBMI_NOTES](../IBMI_NOTES.md#add-column--not-null-without-a-default-probe----add_column_default)
- CPA32B2 suppressed per job with `OVERRIDE_QAQQINI`, around transactions,
  and how narrowing measures; SQL0910 comes from changed rows only: [IBMI_NOTES](../IBMI_NOTES.md#cpa32b2-suppressed-per-job-qaqqini-suppress_inquiry_messages-probe----qaqqini_inquiry), [IBMI_NOTES](../IBMI_NOTES.md#override_qaqqini-around-transactions-and-how-narrowing-measures-probe----qaqqini_lifecycle), [IBMI_NOTES](../IBMI_NOTES.md#sql0910-comes-from-changed-rows-only-lib_pending_change)
- `inspectdb` on tables created with plain SQL: `NUMERIC` and `CLOB` in the
  catalog, `CHAR` values keep their padding: [IBMI_NOTES](../IBMI_NOTES.md#inspectdb-on-tables-created-with-plain-sql-testspub400test_inspectdbpy)
- Unresolved: the constraint name `CONSTRAINT` refused with SQL0601 on
  PUB400, without a catalog row (recorded under the SQL0546 section).

## Test status at the end of the phase
The phase's Django modules on PUB400 (IBM i 7.5), Python 3.14, one
connection at a time, `--clean`, 2026-10-27, on the last commit of the PR
that changed them:

| Module | Django 6.1 | Django 6.0 | Django 5.2 |
|---|---|---|---|
| `migrations` (#184) | 825 tests: 26 skipped, 24 expected failures | 811: 26 skipped, 24 expected failures | 784: 25 skipped, 24 expected failures |
| `schema` (#186) | 227: 92 skipped, 22 expected failures | 222: 89 skipped, 22 expected failures | 220: 87 skipped, 23 expected failures |
| `introspection` (#184, `57b68d1`) | 24: 6 skipped | 21: 3 skipped | 21: 3 skipped |
| `inspectdb` (#186) | 31: 14 skipped | 28: 11 skipped | 28: 11 skipped |
| `migrate_signals` (`main` at `a7860ba`) | 3, all passed | 3, all passed | 3, all passed |

0 failures and 0 errors in each. The expected failures have one reason each
in `features.py` (no column rename, type changes not in place, SQL0910 with
pending row changes, CHECK with LIKE against a column, JSONField on 5.2).
The own IBM i tier on 6.1 (#186): 328 passed, 1 expected failure (the
`DROP COLUMN` inquiry test). The complete status of every supported module
and test set, from one status run on `main` after this phase, is in
[TEST_STATUS](../TEST_STATUS.md).

## Carried forward
- **No table rebuild**: column renames and incompatible type changes stay
  refused (`NotSupportedError`) with their expected failures; a rebuild
  could be an opt-in later ([DECISIONS](../DECISIONS.md#2026-10-26-no-table-rebuild-for-column-renames-and-incompatible-type-changes)).
- **`migration_test_data_persistence` is not a supported module**: on 6.1
  the test app's own migration inserts a row (`RunPython`) and then changes
  the primary key to `BigAutoField` in the same transaction, which Db2 for i
  refuses with SQL0910 while the test database is set up (Known
  limitations, SQL0910); 6.0 and 5.2 pass (3 tests). Before 6.1 the
  migration has no `AlterField`.
- **Flags not evaluated in phase 4**, marked "later" in
  [FEATURES](../FEATURES.md): collations (`supports_collation_on_*`,
  `supports_non_deterministic_collations`), generated columns
  (`supports_stored_generated_columns`, `supports_virtual_generated_columns`,
  `supports_alter_generated_column_data_type`), `supports_unlimited_charfield`,
  `supports_no_precision_decimalfield`, `supports_sequence_reset`,
  `supports_comments_inline`, `can_introspect_materialized_views`,
  `has_real_datatype`, `related_fields_match_type`, `truncates_names`.
- **Phase 5**: unique constraint variants, partial / expression / covering
  indexes, `allows_multiple_constraints_on_same_fields`, the `constraints`,
  `indexes` and `model_indexes` modules.
- **Phase 6**: DB-level `on_delete` (6.1+), JSONField (also the 5.2 schema
  test `test_db_default_output_field_resolving`).
- **On a dedicated IBM i**: Db2 for i's `DROP COLUMN` default for dependent
  objects (needs a system reply list entry).
- **Unresolved on PUB400**: the constraint name `CONSTRAINT` refused with
  SQL0601 without a catalog row ([IBMI_NOTES](../IBMI_NOTES.md#check-with-like-against-a-column-pattern-sql0546-django-migrations)).
- Open issues: [#124](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/124)
  (tables in another library than `NAME`), [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82)
  (`annotations` / `expressions_case`), [#94](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/94)
  (release workflow variable).
- The code rename to the four test set names (one mechanical PR when no
  other PRs are open).

## Links
- [DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md), [FEATURES.md](../FEATURES.md),
  [TEST_STATUS.md](../TEST_STATUS.md), [WORKFLOW.md](../WORKFLOW.md),
  [Known limitations](../user/Known-Limitations.md),
  [IBM i requirements](../user/IBM-i-Requirements.md).
- Changelog: the fragments in `changelog.d/` until the next release.
- The approved plan: this file from the merge of #123 until #187.
