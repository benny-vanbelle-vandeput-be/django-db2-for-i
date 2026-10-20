# Phase 4: Schema editor completeness

> Status: Proposed, not yet approved

This is a proposal, not yet a record. It follows the phase template in
[README.md](README.md) and the layout of the approved phase 3 plan (commit
`650b508`, before [phase-3.md](phase-3.md) became the record). The open questions for the maintainer are at the
end; nothing in this plan is implemented before it is approved.

The analysis reads three Django checkouts (shallow clones of the stable
branches):

| Branch | Commit | Version |
|---|---|---|
| `stable/6.1.x` | `9f52f9a`, 2026-10-20 | 6.1.3 alpha |
| `stable/6.0.x` | `52e5ba1`, 2026-10-09 | 6.0.10 alpha |
| `stable/5.2.x` | `cae7247`, 2026-10-09 | 5.2.19 alpha |

They are compared against the backend on `main` at `59991df`.

## Goal
From CLAUDE.md section 9: **schema editor completeness**: `schema`,
`migrations`, `introspection`, `inspectdb`. Also: verify the column order of
created tables ([#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23)).

Carried into this phase:
- from phase 3: `get_relations()` 3-tuples with `db_on_delete` (Django 6.1),
  shaped through `compat.py`, and `supports_inspectdb`;
- from phase 1: the open question whether data-losing `ALTER TABLE` needs a
  table rebuild ([DECISIONS](../DECISIONS.md#2026-10-17-open-question-for-phase-4-table-rebuild-for-data-losing-alter-table));
- from phase 2: foreign key violations (SQL0530 / SQL0531 / SQL0532) mapped to
  `IntegrityError` ([#96](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/96));
- from [Known limitations](../user/Known-Limitations.md#tables-must-be-in-the-library-given-as-name):
  tables in another library than `NAME` "planned for phase 4" (open
  question 8).

Proposed "done when":
- the Django modules `introspection`, `inspectdb` and `schema`, and the
  database parts of `migrations`, run on 6.1, 6.0 and 5.2 against PUB400
  without failures or errors: every remaining failure is a skip or expected
  failure with a fixed reason, and the list of each is reviewed;
- the phase 4 flags are on where the tests back them, each with its own
  pub400 test of the common real-world pattern;
- DDL goldens exist for every migration operation the backend supports, per
  Django series, verified on PUB400;
- issue #23 is answered (offline golden, pub400 check, user docs) and the
  foreign key part of #96 is done;
- the CPA32B2 / table rebuild question has a recorded decision.

## What was done
Nothing yet. The planned work follows.

### 1. Where the backend stands

**Schema editor** (`schema.py`, 173 lines): `CREATE` / `DROP TABLE`, column
defaults as bare literals, `ADD COLUMN`, `DROP COLUMN` (pinned for every
Django version), `COMMENT ON` through `quote_value()`, and the CPA32B2
explanation for a cancelled `ALTER TABLE` (`inquiry.py`). Every other
statement comes from Django's `BaseDatabaseSchemaEditor` templates,
untested on Db2 for i:

| Template (Django 6.1 base) | Base SQL | Known on Db2 for i |
|---|---|---|
| `sql_alter_column_type` | `ALTER COLUMN c TYPE t` | not probed |
| `sql_alter_column_null` / `_not_null` | `ALTER COLUMN c DROP NOT NULL` / `SET NOT NULL` | not probed |
| `sql_alter_column_default` / `_no_default` | `ALTER COLUMN c SET DEFAULT d` / `DROP DEFAULT` | not probed |
| `sql_rename_column` | `ALTER TABLE t RENAME COLUMN a TO b` | not probed |
| `sql_rename_table` | `ALTER TABLE a RENAME TO b` | not probed |
| `sql_rename_index` | `ALTER INDEX a RENAME TO b` | not probed |
| `sql_create_fk` | `ALTER TABLE t ADD CONSTRAINT n FOREIGN KEY ...` | **works** (golden `ddl/create_node_fk`, verified 2026-10-19; pub400 `test_foreign_keys_are_no_action`) |
| `sql_create_unique`, `sql_create_check`, `sql_delete_constraint` | `ALTER TABLE t ADD / DROP CONSTRAINT n ...` | constraints need a journaled table (SQL7008 in QTEMP); unqualified names resolve to `NAME` (SQL5051) |
| `sql_create_index`, `sql_delete_index` | `CREATE INDEX n ON t (...)`, `DROP INDEX n` | `CREATE INDEX` works (FK index in the golden above) |
| `sql_delete_table` | `DROP TABLE t CASCADE` | drops dependent views and foreign keys ([IBMI_NOTES](../IBMI_NOTES.md#drop-table-with-foreign-keys-and-views-probe_drop)) |

The column `CHECK` constraints of `data_type_check_constraints`
(`PositiveIntegerField` and friends) are already written into `CREATE TABLE`,
and SQL0545 is already mapped to `IntegrityError` (`drivers/base.py`), while
`supports_column_check_constraints` is still off. Foreign keys are written
only where a test switches `supports_foreign_keys` on (the pub400 tier's
test tables and the DDL goldens).

**Introspection** (`introspection.py`, 74 lines): `get_table_list()`,
`get_table_description()` (column order by `ORDINAL_POSITION`, which #23
asks to check) and `get_sequences()`. **Missing:** `get_constraints()`,
`get_relations()`, `data_types_reverse` and `introspected_field_types`.
Django's schema editor calls `get_constraints()` (through
`_constraint_names()`) whenever it changes or drops a constraint, an index
or a foreign key, for example in `alter_field()`, `remove_field()` on a
foreign key, `alter_unique_together()` and `alter_index_together()`; those
paths raise `NotImplementedError` today. This is the first gap to close.

**What is known about CPA32B2** ([IBMI_NOTES](../IBMI_NOTES.md#alter-table-cancelled-by-cpa32b2-probe_inquiry-probe_job_reuse),
probes `w08_inquiry`, `w09_job_reuse`, `p23_drop_column`;
[IBM i requirements](../user/IBM-i-Requirements.md)):
- `DROP COLUMN` and narrowing column changes (INTEGER → SMALLINT, shorter
  `VARCHAR` / `NVARCHAR`, smaller `DECIMAL`) send inquiry message CPA32B2,
  also on empty tables; the default reply C cancels them (HY008).
- Widening changes and `ADD COLUMN ... NOT NULL DEFAULT 0` are not affected.
  Other changes (`DROP NOT NULL`, `SET NOT NULL`, defaults, renames, type
  changes between families) are **not probed yet**.
- `OPTIONS["inquiry_message_reply"] = "*SYSRPYL"` helps only with a system
  reply list entry `MSGID(CPA32B2) RPY('I')`, which PUB400 does not have and
  which a normal user cannot add.
- Db2 for i asks CPA32B2 before it looks at dependent objects, so its default
  for `DROP COLUMN` (CASCADE or RESTRICT) is unknown on PUB400.

### 2. Django test modules
Test counts are `def test_` definitions in the checkouts. They match the
counts `runtests.py` reports for most modules (`queries`: 506 on 6.1 in both),
but not where test classes are reused by subclasses (`transactions`: 41
definitions, 88 tests run). The main session records the real counts with
the first run of each module.

**The phase 4 modules:**

| Module | 5.2 | 6.0 | 6.1 | Touches the database | Notes |
|---|---|---|---|---|---|
| `introspection` | 21 | 21 | 24 | all | needs `get_constraints()`, `get_relations()`, `get_field_type()` |
| `inspectdb` | 28 | 28 | 31 | most | on 5.2 and 6.0 there is no `supports_inspectdb`, so every test runs whatever the flag says |
| `schema` | 220 | 222 | 227 | all | about 99 tests call `alter_field()`, 6 call `remove_field()` (6.1) |
| `migrations` | 784 | 811 | 827 | part | see below |
| `migrate_signals` | 3 | 3 | 3 | all | small |
| `migration_test_data_persistence` | 3 | 3 | 3 | all | small; data migrations |

`migrations` per file (6.1): `test_operations` 180 (about 37 with
`AlterField`, 8 with `RemoveField`), `test_commands` 162 (most run
`migrate`), `test_executor` 24, `test_multidb` 10 (needs the `other`
library), `test_loader` 28. The rest does not touch the database:
`test_autodetector` 176, `test_writer` 74, `test_state` 85, `test_optimizer`
52, `test_graph` 20, `test_questioner` 14. Proposal: run `migrations` as
labels (`migrations.test_operations`, `migrations.test_executor`,
`migrations.test_commands`, `migrations.test_multidb`,
`migrations.test_loader`), and leave the files that do not touch the
database to runs on other backends (they test Django, not the backend); open
question 6.

**Related modules** that the new flags affect, run once per flag change, not
owned by this phase: `model_options` (24, `db_table`, `db_table_comment`),
`field_defaults` (18, `db_default`), `delete` (64) and `delete_regress` (22)
and `nested_foreign_keys` (7) and `null_fk` (2) (database foreign keys on),
`backends` (325, constraint checks and introspection helpers), and the seven
supported modules of [TEST_STATUS](../TEST_STATUS.md), which must stay green
when `supports_foreign_keys` is switched on. `constraints` (102), `indexes`
(31) and `model_indexes` (30) belong to phase 5 (open question 1).

**Tests behind flags that are off** (6.1, `skipUnlessDBFeature`):

| Module | Flag (number of tests) |
|---|---|
| `schema` | `supports_expression_indexes` (24 + 6 combined), `supports_foreign_keys` (13 + 5 with `can_introspect_foreign_keys` + 2 with `supports_comments` + 1 with `indexes_foreign_keys`), `supports_collation_on_charfield` (7), `supports_comments` (5 + 3 combined), `supports_stored_generated_columns` (3 + 2 combined), `can_create_inline_fk` (2 + 1 with `supports_on_delete_db_cascade`), `allows_multiple_constraints_on_same_fields` (2), `supports_index_on_text_field`, `supports_collation_on_textfield`, `supports_virtual_generated_columns`, `supports_nulls_distinct_unique_constraints`, `ignores_table_name_case`, `can_defer_constraint_checks` with `can_rollback_ddl` (1 each) |
| `migrations` | `supports_table_check_constraints` (6), `supports_stored_generated_columns` (6), `supports_foreign_keys` (5 + 2 with collation), `supports_virtual_generated_columns` (4), `allows_multiple_constraints_on_same_fields` (4), `supports_expression_indexes` (3), `supports_expression_defaults` (2), `supports_covering_indexes`, `supports_comments`, `ignores_table_name_case`, `can_rollback_ddl` (1 each) |
| `introspection` | `can_introspect_foreign_keys` (1 + 3 with `supports_on_delete_db_*`), `supports_index_column_ordering` (1 + 1 with partial indexes), `supports_comments`, `has_real_datatype` (1 each) |
| `inspectdb` | `supports_inspectdb` (2, and 1 `skipIfDBFeature`), `can_introspect_foreign_keys` (2), `supports_unlimited_charfield`, `supports_no_precision_decimalfield`, `supports_expression_indexes`, `supports_comments`, `supports_collation_on_charfield` / `_on_textfield`, `can_introspect_materialized_views`, `can_introspect_json_field` (1 each) |

Many more tests branch on `connection.features.*` inside the test
(`introspected_field_types` 24 times in `schema`,
`supports_index_column_ordering` 9, `supports_foreign_keys` and
`can_introspect_foreign_keys` 7 each, `can_introspect_default` 4).

### 3. Feature flags phase 4 will touch
From [FEATURES.md](../FEATURES.md) and `features.py`. "Planned" flags are
marked `planned = "phase 4"` in [features.toml](../features.toml); this PR
adds descriptions for the ones below that lacked them.

**Planned for phase 4, to be switched on when the tests back them:**

| Flag | Depends on |
|---|---|
| `can_introspect_foreign_keys` | `get_relations()`, `get_constraints()` |
| `can_introspect_check_constraints` | `get_constraints()` reading `QSYS2.SYSCHKCST` |
| `can_introspect_default` | parsing `SYSCOLUMNS.COLUMN_DEFAULT` back into Django's form |
| `supports_inspectdb` (6.1 only) | `data_types_reverse`, `get_relations()` |
| `supports_foreign_keys` | FK violations mapped (#96), the supported modules still green |
| `indexes_foreign_keys` | whether Db2 for i makes its own index for a foreign key (probe) |
| `can_create_inline_fk` | open question 4 |
| `supports_column_check_constraints` | already written into `CREATE TABLE`; needs introspection |
| `supports_table_check_constraints` | `CheckConstraint` add / remove (journaled library) |
| `allows_multiple_constraints_on_same_fields` | Db2 for i behaviour with two constraints on the same columns (probe) |
| `supports_index_column_ordering` | `DESC` in `CREATE INDEX` and in the catalog (probe) |
| `supports_index_on_text_field` | whether an `NCLOB` column can be an index key (probe) |
| `supports_sequence_reset` | `sequence_reset_sql()` exists (phase 1); the flag only gates its tests |
| `can_rename_index` (new in the plan) | a `RENAME INDEX` form (probe) |
| `supports_comments` (new in the plan) | `COMMENT ON` works for text in the job CCSID (open question 7) |

**Looked at, decided by a probe or left off with a reason:**
`supports_combined_alters` (several clauses in one `ALTER TABLE`; fewer
statements and fewer CPA32B2 points), `connection_persists_old_columns`,
`supports_comments_inline`, `related_fields_match_type`,
`ignores_table_name_case`, `supports_unlimited_charfield`,
`supports_no_precision_decimalfield` (6.1), `supports_collation_on_charfield`
/ `_on_textfield`, `supports_expression_defaults` (stays off: a column
`DEFAULT` takes only a constant or special register, IBMI_NOTES),
`supports_stored_generated_columns` / `supports_virtual_generated_columns` /
`supports_alter_generated_column_data_type`, `can_introspect_materialized_views`,
`has_real_datatype`, `can_defer_constraint_checks` (stays off:
nothing is deferrable), `can_rollback_ddl` (stays off unless a probe in a
journaled library shows otherwise; open question 3). Each gets a reason in
`features.toml` when it is decided.

**Not a boolean, so not in FEATURES.md:** `introspected_field_types` (a dict
the `schema` and `inspectdb` tests read to know which Django field type comes
back for each column type), set from the type mapping in `base.py`.

### 4. IBM i questions and probes
Never guessed. QTEMP probes may run without approval; everything that needs a
constraint needs a journaled library and the maintainer's approval (QTEMP
tables take no constraints, SQL7008).

**Probe 24, `alter_table` (QTEMP, no approval needed):** on a QTEMP table with
one row, the job reply left at `*RQD` (so CPA32B2 shows as HY008 and nothing
changes), for each statement: valid syntax or not, CPA32B2 or not, result.
- `ALTER COLUMN c TYPE t` and `ALTER COLUMN c SET DATA TYPE t`, for widening,
  narrowing and cross-family changes (INTEGER ↔ BIGINT, INTEGER ↔ DECIMAL,
  NVARCHAR ↔ NCLOB, NVARCHAR length, DECIMAL precision and scale, BOOLEAN);
- `DROP NOT NULL`, `SET NOT NULL` (with and without NULLs in the data),
  `SET DEFAULT`, `DROP DEFAULT`;
- `RENAME COLUMN`, `ALTER TABLE ... RENAME TO`, `RENAME TABLE ... TO`, and
  the system name of the renamed table;
- index rename: `ALTER INDEX ... RENAME TO`, `RENAME INDEX ... TO`;
- identity changes Django needs when a field becomes or stops being an
  `AutoField` (`ADD` / `DROP IDENTITY`, `SET GENERATED`);
- several clauses in one `ALTER TABLE` (`supports_combined_alters`);
- where `ADD COLUMN` puts the new column (always last?) and the column order
  of `CREATE TABLE` in `SYSCOLUMNS` (#23);
- `CREATE INDEX` with `DESC`, on an `NCLOB` column, and with a long name
  (the system name Db2 for i gives the index);
- the real maximum row length (`SQL_MAX_ROW_SIZE` reports 32740, DECISIONS
  uses 32,766; IBMI_NOTES asked for a DDL probe in phase 4).

**Probe 25, `catalog` (read-only, no approval needed):** the columns of
`QSYS2.SYSINDEXES`, `SYSKEYS`, `SYSCST`, `SYSKEYCST`, `SYSCHKCST`,
`SYSREFCST` and `SYSCOLUMNS` that `get_constraints()`, `get_relations()` and
`can_introspect_default` need (types, which values mean what, ordering
columns), read from the views' own `SYSCOLUMNS` rows as in
`probe_operations`, and whether QTEMP objects appear in these views.

**Probe w13, `constraints` (journaled `default` library, needs approval):**
creates its own tables with a prefix, drops them at the end, one connection:
- a foreign key violation of each kind (insert or update a child with a
  missing parent, delete or update a referenced parent) and the SQLSTATE /
  SQLCODE the driver reports (SQL0530 / SQL0531 / SQL0532, #96);
- whether Db2 for i creates or shares an index for a foreign key
  (`indexes_foreign_keys`);
- two constraints on the same columns (a unique constraint and a unique
  index; two foreign keys);
- a table `CHECK` constraint add and drop, and how `SYSCHKCST` records it;
- `DROP COLUMN` on a column with a foreign key or check constraint is only
  observable with a CPA32B2 reply list entry, so it is not part of w13;
- whether DDL under commitment control is rolled back (`can_rollback_ddl`;
  open question 3).

Alternative to w13: the same checks as pub400 tests on the tier's own test
tables, which already have foreign keys (open question 3).

**Needs a dedicated IBM i** (not planned on PUB400): `DROP COLUMN` and
narrowing changes with a CPA32B2 reply list entry and
`OPTIONS["inquiry_message_reply"] = "*SYSRPYL"`, including Db2 for i's
default for dependent objects; the full tier.

### 5. Design

**Introspection.**
- `get_constraints()` from the catalog of the connection's `CURRENT SCHEMA`
  (like the other introspection queries), returning primary keys, unique
  constraints, check constraints, foreign keys and indexes in Django's
  format, with names through `identifier_converter()`. Index column order
  (`ASC` / `DESC`) only if probe 25 shows where it is recorded.
- `get_relations()` from `SYSREFCST` joined to `SYSKEYCST`. The tuple shape
  depends on the Django version, so `compat.py` provides it, in the section
  "Before 6.1: Django 6.0 and 5.2": on 6.1 `(column, table, db_on_delete)`,
  with `SYSREFCST.DELETE_RULE` mapped to `DB_CASCADE`, `DB_SET_NULL`,
  `DB_SET_DEFAULT` or `DO_NOTHING` the way Django's own backends do; on 6.0
  and 5.2 `(column, table)`. Introspection calls one compat function and
  never checks the version itself.
- `data_types_reverse` and `get_field_type()`: from `SYSCOLUMNS.DATA_TYPE`
  plus length, precision, scale and `IS_IDENTITY` back to Django fields
  (`NVARCHAR` → `CharField`, `NCLOB` → `TextField`, identity `INTEGER` /
  `BIGINT` / `SMALLINT` → `AutoField` / `BigAutoField` / `SmallAutoField`,
  `BOOLEAN` → `BooleanField`, ...). `introspected_field_types` follows from
  the same table.
- `get_table_description()` completed: display size, internal size, the
  default in Django's form (for `can_introspect_default`), `collation` stays
  `None`.

**Schema editor.**
- The `ALTER` templates overridden only where probe 24 shows that Db2 for i
  needs another form, each with a DDL golden per Django series.
- `CREATE TABLE` must follow `Model._meta.local_fields` exactly; the backend
  does not reorder columns (#23). `ADD COLUMN` appends at the end, as on
  every Django backend; documented in the user docs.
- Foreign keys stay `ALTER TABLE ... ADD CONSTRAINT` with Db2's default
  `NO ACTION` ([DECISIONS](../DECISIONS.md#2026-10-17-foreign-keys-use-db2s-default-no-action)).
  Django 6.1's `on_delete` SQL in `sql_create_fk` stays empty while the
  `supports_on_delete_db_*` flags are off (phase 6).
- Constraint and index names stay unqualified, so they resolve to `NAME`
  (SQL5051 otherwise). Tables in another library would need qualified names
  (open question 8).

**CPA32B2 and table rebuilds.** Three options:
1. **Keep the current design** (recommended for phase 4): the opt-in reply
   list setting, the explained `OperationalError`, and the Django tests that
   drop columns or narrow them marked as expected failures with one fixed
   reason ("CPA32B2: no system reply list entry on PUB400"). The tests move
   to passing on a dedicated IBM i with the entry, with no code change.
2. **An opt-in rebuild** for data-losing changes only, as Django does for
   SQLite (`_remake_table`): create the new table, copy the rows, drop the
   old one, rename. On Db2 for i the rebuild would have to recreate indexes,
   constraints, foreign keys pointing at the table, views (which `DROP
   TABLE` drops silently), triggers, authorities, the journaling and the
   identity's next value, and keep the system name. Each needs probes
   (several outside QTEMP); it must never run silently on production data.
3. **Rebuild only in Django's test runs**: hides the behaviour users will
   meet; not recommended.

With option 1 the phase can still decide on option 2 later, from the number
of expected failures it leaves. Open question 2.

**Comments.** `COMMENT ON` works for text in the job CCSID and rejects other
characters (SQL0104; IBMI_NOTES, encoding investigation). Switching on
`supports_comments` means documenting that limitation (open question 7).

### 6. Test strategy
- **Offline tier**, every commit, every Python × every Django version:
  - DDL goldens (`connection.schema_editor(collect_sql=True)`) for each
    migration operation: `AddField`, `AlterField` (type, null, default,
    rename), `RemoveField`, `RenameField`, `RenameModel`, `AlterUniqueTogether`,
    `AddIndex` / `RemoveIndex` / `RenameIndex`, `AddConstraint` /
    `RemoveConstraint` (check), foreign key add / remove, the #23 model with a
    mixin and an abstract base. Per series (`golden/<series>/7.5/ddl/...`).
  - Unit tests of the introspection methods with a fake cursor returning
    catalog rows, including the compat-shaped `get_relations()` on each
    version.
  - Every golden is verified on PUB400 by the pub400 tier's golden job.
- **pub400 tier**: the full tier on every backend PR (newest Python, newest
  Django during development, as CLAUDE.md says; the PR states the SHA and
  counts). Each enabled flag gets its own test of the real-world pattern, for
  example: with `supports_foreign_keys`, deleting a referenced `Author`
  through the ORM with `on_delete=PROTECT` and through raw SQL, and creating a
  `Book` for a missing author, both raising `IntegrityError`; with
  `supports_inspectdb`, `inspectdb` on the tier's tables giving models whose
  fields match the originals; with `can_introspect_foreign_keys`,
  `get_relations()` on the tier's tables.
- **Django modules on PUB400**: run by the main session, one module or label
  per run, `--parallel=1`, always `--clean`, never two PUB400 jobs at once.
  6.1 first; 6.0 and 5.2 at the end of each step group (section 7). A
  baseline run of `introspection` and `schema` on 6.1 before step B, so the
  plan starts from real failures (open question 10).
- **Release run**: the modules that join the supported list (open question 6)
  are added to the `release_run` list in code.
- **Full tier**: only on a dedicated IBM i (CPA32B2 tests, `CREATE SCHEMA`
  test databases).

### 7. Plan with PR boundaries
Each PR is small and reviewable; backend PRs carry `needs-full-tier` until
the full pub400 tier on their latest commit is posted. Probes come first
wherever Db2 for i behaviour is unknown.

**Step A: facts first**
1. `test(probes)`: probe 24 `alter_table` (QTEMP) and probe 25 `catalog`
   (read-only); findings in IBMI_NOTES. No backend change.
2. `test(probes)`: probe w13 `constraints` in the journaled `default`
   library, **only after approval** (open question 3); findings in
   IBMI_NOTES.
3. `test`: issue #23: the offline golden for a model with a mixin and an
   abstract base, a pub400 check of the order in `QSYS2.SYSCOLUMNS`, and the
   user docs (column order follows field creation order). A backend change
   only if the check finds a reordering.

**Step B: introspection** (6.1, then 6.0 and 5.2)
4. `feat(introspection)`: `get_constraints()` and `get_primary_key_column()`,
   unit tests and a pub400 test on the tier's tables. This unblocks
   `alter_field()` and `remove_field()` paths in the schema editor.
5. `feat(introspection)`: `get_relations()` with the compat shape, then
   `can_introspect_foreign_keys` on, with its pub400 test.
6. `feat(introspection)`: `data_types_reverse`, `get_field_type()`,
   `introspected_field_types`, `get_table_description()` completed,
   `can_introspect_default` and `can_introspect_check_constraints` on (each
   with a pub400 test). Django `introspection` on 6.1, 6.0 and 5.2.

**Step C: schema editor** (6.1, then 6.0 and 5.2)
7. `feat(schema)`: the `ALTER COLUMN` forms from probe 24 (type, null,
   default), with goldens and pub400 tests for a migration that alters a
   field and back.
8. `feat(schema)`: renames (column, table, index; `can_rename_index`),
   identity changes, `supports_combined_alters` if probe 24 allows it.
9. `feat(schema)`: CPA32B2 per the decision on open question 2; with
   option 1, the expected failures with one fixed reason, listed per Django
   version, and the user docs.
10. `feat(schema)` + `fix(driver)`: foreign keys: SQL0530 / SQL0531 / SQL0532
    mapped to `IntegrityError` (#96), `supports_foreign_keys` on, and
    `indexes_foreign_keys` / `can_create_inline_fk` as decided (open
    questions 4 and 5). The seven supported modules rerun on 6.1 before the
    PR is ready, since database foreign keys change their behaviour.
11. `feat(schema)`: check constraints: `supports_column_check_constraints`
    and `supports_table_check_constraints`, plus
    `allows_multiple_constraints_on_same_fields` if w13 allows it. Each with a
    pub400 test (a `PositiveIntegerField` going negative; a model
    `CheckConstraint` violated through `save()`).
12. `feat(schema)`: indexes from probe 24: `supports_index_column_ordering`,
    `supports_index_on_text_field` where possible.
13. `feat(schema)`: `supports_comments` if approved (open question 7).
14. `test`: Django `schema` and the `migrations` labels on 6.1, then 6.0 and
    5.2; the per-version lists shrink.

**Step D: inspectdb**
15. `feat(introspection)`: `supports_inspectdb` on (6.1), with a pub400 test.
    On 6.0 and 5.2 the `inspectdb` tests run regardless of the flag, so their
    remaining failures get per-version entries. Django `inspectdb` on all
    three versions.

**Close**
16. `docs`: the user docs (column order, CPA32B2 expectations, foreign keys
    and check constraints in the database, known limitations), the phase 4
    record, the changelog fragments, `docs/status.toml` and the generated
    status (main session), and the new modules in the release run.

## Key decisions
None yet. The decisions taken on the open questions will be recorded in
[DECISIONS.md](../DECISIONS.md) and linked here.

## IBM i findings
None yet. Probes 24 and 25 (QTEMP and read-only) and, if approved, w13 will
add their findings to [IBMI_NOTES.md](../IBMI_NOTES.md).

## Test status at the end of the phase
Not started. Baseline: see [TEST_STATUS.md](../TEST_STATUS.md) (seven
supported modules on 6.1, 6.0 and 5.2; none of the phase 4 modules has been
run yet).

## Carried forward
To be filled at the end of the phase. Known candidates:
- the table rebuild (option 2) if it is not done in this phase;
- DB-level `on_delete` and the `supports_on_delete_db_*` flags (phase 6);
- unique constraint variants, partial / expression / covering indexes and the
  `constraints`, `indexes` and `model_indexes` modules (phase 5, open
  question 1);
- the CPA32B2 tests and Db2 for i's `DROP COLUMN` default for dependent
  objects on a dedicated IBM i.

## Links
- [CLAUDE.md](../../CLAUDE.md) sections 2, 5, 6 and 9;
  [DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md) (6.1: `get_relations()`,
  `supports_inspectdb`); [FEATURES.md](../FEATURES.md).
- Issues [#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23)
  and [#96](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/96).
- [IBMI_NOTES](../IBMI_NOTES.md): CPA32B2, `DROP COLUMN` with and without
  CASCADE, constraint violations, `DROP TABLE` with foreign keys and views,
  SQL catalog views in a library.
- Django release notes: `docs/releases/6.1.txt` ("Database backend API").

## Open questions
1. **Phase 4 or phase 5 for constraints and indexes?** CLAUDE.md lists
   "constraints, indexes" under phase 5, while `features.toml` plans the check
   constraint and index flags for phase 4. Proposal: phase 4 does what
   `schema`, `migrations`, `introspection` and `inspectdb` need (foreign
   keys, check constraints, introspection of every constraint, index
   ordering and text-field indexes); phase 5 keeps unique constraint
   variants, partial / expression / covering indexes and the `constraints`,
   `indexes` and `model_indexes` modules. Agreed?
2. **CPA32B2: keep the opt-in reply list and mark the affected tests as
   expected failures (option 1), or build an opt-in table rebuild now
   (option 2)?** The recommendation is option 1, deciding on option 2 from
   the number of expected failures at the end of step C.
3. **Probe w13 in the journaled `default` library**: approve it (own
   prefixed tables, dropped at the end, one connection), or do the same
   checks as pub400 tests on the tier's own tables? Should it include the
   `can_rollback_ddl` check?
4. **`can_create_inline_fk`**: keep foreign keys as separate `ALTER TABLE
   ... ADD CONSTRAINT` statements (verified on PUB400, the flag stays off;
   3 `schema` tests skipped), or write them inline in `CREATE TABLE`?
5. **`indexes_foreign_keys`**: if w13 shows that Db2 for i creates or shares
   an index for a foreign key, should the backend stop creating Django's own
   index for foreign key columns? That changes the DDL of existing projects'
   new migrations.
6. **Which modules join the supported list and the release run?**
   Proposal: `introspection`, `inspectdb`, `schema`, `migrate_signals`,
   `migration_test_data_persistence`, and `migrations` as the five database
   labels of section 2. This makes each release run noticeably longer on
   PUB400.
7. **`supports_comments`**: switch it on in phase 4 with the documented
   limitation (comment text must fit the job CCSID, SQL0104 otherwise), or
   keep it off?
8. **Tables in another library than `NAME`** (Known limitations says
   "planned for phase 4"): in scope now (qualified constraint and index
   names), or moved to a later phase?
9. **6.0 and 5.2 per PR or per step group?** Proposal: goldens for all three
   series in each PR (offline), the Django modules on 6.0 and 5.2 at the end
   of each step group, as in section 7.
10. **Baseline runs**: may the main session run `introspection` and `schema`
    on 6.1 once before step B, to start from real failures? `schema` is the
    heaviest module so far (227 tests, DDL in every test).
