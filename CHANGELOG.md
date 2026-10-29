# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Changes since the last release are in [changelog.d/](changelog.d/), one
fragment per pull request; they are assembled here at release time.

## [0.1.0b1] - 2026-10-29

### Added
- Every pull request is classified from its changed files (needs full tier,
  SQL-affecting, docs/tests only) by `scripts/classify_pr.py`; the CI job
  `classify` comments the result and adds the labels `needs-full-tier` and
  `run-ibmi` that decide which IBM i run a pull request needs
  (CONTRIBUTING.md, "Pull requests and IBM i runs"). (#126)
- A verification gate in CI (`nox -s gate`): every golden and corpus entry must
  carry a verification stamp, except the goldens in
  `tests/offline/golden/unverifiable.toml`, each with its reason and the
  condition under which it becomes verifiable; TEST_STATUS shows their count.
  The status generator ignores logs outside the current run set (modules not
  supported yet, leftovers of older layouts). (#127)
- `bin/check` (what CI does, locally) and `bin/status` (status pages, the
  PUB400 lock holder, the pull requests waiting for an IBM i run), with
  `--help` and `--dry-run`. Every PUB400 run holds a lock outside the checkout
  (`scripts/pub400.sh`, `scripts/pub400_lock.py`): a second job stops with
  "PUB400 busy: <holder>", or waits with `--wait`. (#128)
- `bin/doctor` (environment check and one PUB400 connection), `bin/probe`
  (read-only probes by name), `bin/ibmi-test` (own IBM i tests, Django test
  labels or the full tier) and `bin/ibmi-cleanup` (drops the leftover test
  objects of a crashed run, only those test runs listed before creating them,
  only in a library with the test marker table), all through the PUB400 lock.
  The own IBM i test modules now write the marker before they create their
  tables, so `bin/ibmi-cleanup` also covers a crash in any of them. (#129)
- `bin/verify`: runs the offline tests and the corpus replay, writes changed SQL
  to the goldens and corpus, then runs exactly what needs IBM i (unverified
  goldens, new or changed own IBM i tests, one Django test per unverified corpus
  entry, tests that left the skip lists) and writes the stamps of what passed to
  the working tree, with a report. `bin/ibmi-test --affected` runs the same
  selection without writing stamps. Git inside the container now trusts only the
  checkout's mount (`/workspace`), which fixes "dubious ownership" in `bin/check`. (#130)
- `bin/setup`: first-time setup: images, `.env` from `.env.example` (values
  typed in a terminal; an existing `.env` is never touched), the `vendor/`
  Django checkouts at their pinned commits, then `bin/doctor --offline`. (#131)
- `bin/release-run`: the release run per Django version, resumable: results
  are recorded as they come, and a later start on the same commits skips what
  passed (`--restart`, `--limit N`); the corpus is rebuilt when a version
  passed completely. (#131)
- `bin/release-prepare <version>`: checks the release preconditions and opens
  the release pull request; it never tags and never creates releases, and
  prints the maintainer's manual steps. (#131)
- `docs/WORKFLOW.md`, the workflow guide: a quick start (the five commands of
  a change) and topics from setup to release, with the exact commands;
  `bin/help` shows the quick start and the topics, `bin/help <topic>` one of
  them. README and CONTRIBUTING list every `bin/` script in one table. (#132)
- Column order of created tables verified (issue #23): `CREATE TABLE` follows
  the model's fields (`_meta.local_fields`) exactly, also with fields from
  abstract base classes and mixins; Troubleshooting explains why such fields
  usually come first, and that `AddField` appends at the end. (#136)
- `bin/worktree-remove` removes a merged worktree after copying its
  `test-results/` to the main checkout (`test-results/archive/<worktree>/`);
  `bin/probe --publish` puts a probe result into the repository
  (`probes/results/<probe>.json`) with host, user and library names replaced. (#137)
- Introspection reads constraints and indexes: `get_constraints()` returns the
  primary key, unique, foreign key and check constraints and the indexes of a
  table (with the column order of each index) from the `QSYS2` catalog, and
  `get_primary_key_column()` follows from it. (#138)
- Introspection finds foreign keys: `get_relations()` reads them from the `QSYS2`
  catalog (on Django 6.1 with the delete rule as `db_on_delete`), and
  `can_introspect_foreign_keys` is on. (#140)
- Probe w14 (`nox -s probe_column_types`) records how the `QSYS2` catalog
  describes each column type, identity and default the backend writes
  (docs/IBMI_NOTES.md). (#141)
- Introspection maps every column type the backend writes back to a Django
  field (`data_types_reverse`, identity columns as `AutoField` /
  `BigAutoField` / `SmallAutoField`), reports character lengths and column
  defaults, and `can_introspect_default` and `can_introspect_check_constraints`
  are on, so `inspectdb` writes fields with the right types and lengths. (#144)
- `AlterField` changes that widen a column (a longer `max_length`, a larger
  integer or decimal type), make it nullable or change its default work on
  Db2 for i: the schema editor writes `ALTER COLUMN ... SET DATA TYPE`. The
  CPA32B2 error for narrowing changes and `NOT NULL` now names `NOT NULL` and
  points to the documentation; Known limitations explains that a cancelled
  change to `NOT NULL` can leave NULLs set to the default. (#146)
- `RenameModel` / `AlterModelTable` (`RENAME TABLE`) and `RenameIndex`
  (`RENAME INDEX`, `can_rename_index`) work, and so do identity changes in
  `AlterField`: AutoField to IntegerField drops the identity, IntegerField to
  AutoField adds it and continues after the largest key, and AutoField to
  BigAutoField widens it. Renaming a column raises `NotSupportedError`: Db2 for
  i has no statement for it; keep the column with `db_column` (Known
  limitations). (#147)
- System check `django_db2_for_i.W001`: a warning when new tables in the library of an alias (`NAME` or `TEST["NAME"]`) would not be journaled, because it has no `QSQJRN` journal and isn't journaled with `STRJRNLIB`. Without a journal, transactions and constraints fail with SQL7008. `django_db2_for_i.W002` means the state couldn't be read. Both can be silenced with `SILENCED_SYSTEM_CHECKS`. `bin/doctor` runs the same check on both test libraries. (#157)
- CI: the commit status `ibmi-gate`. It is red while a pull request needs an
  IBM i run and no posted run result (a comment with the `ibmi-run` marker by
  the machine account or the maintainer) covers its current content, so a
  missing label can't let a pull request through. It always runs main's
  workflow and script, and treats the pull request only as data. (#161)

### Enabled features
- Check constraints (`supports_column_check_constraints`,
  `supports_table_check_constraints`): model `CheckConstraint`s are created
  in `CREATE TABLE` and by `AddConstraint` / `RemoveConstraint`, and a
  violation raises `IntegrityError` (SQL0545). Tables need a journal for
  constraints (SQL7008 otherwise; IBM i requirements). (#155)
- `can_rollback_ddl`: migrations run in one transaction. When a statement fails or is cancelled (for example by CPA32B2), the earlier operations of the same migration are rolled back too, including data changes such as the `UPDATE` before `SET NOT NULL`. `sqlmigrate` prints no start statement, because Db2 for i has none. (#158)
- `supports_foreign_keys`: migrations create a foreign key constraint for every
  `ForeignKey` and `OneToOneField`, as a separate `ALTER TABLE ... ADD
  CONSTRAINT` statement. Violations raise `IntegrityError`. Introspection
  (`inspectdb`, the schema editor) does not report a foreign key that Db2 for i
  no longer enforces. See Known limitations for exact type matching (SQL0538),
  fixtures that refer to rows loaded later, and constraint checks that can't be
  switched off. (#170)
- `supports_index_column_ordering`: an index on `Index(fields=["-field"])` is
  created with `DESC` (until now the order was dropped), and introspection
  reports each column's order. (#178)
- `supports_inspectdb` and `ignores_table_name_case`: `manage.py inspectdb`
  writes models for existing tables (also with `NUMERIC` and `CLOB` columns,
  which are now introspected as `DecimalField` and `TextField`), and a
  `db_table` that differs only in case is the same table. (#186)

### Changed
- A push whose own files are docs/tests that do not run on IBM i (such as a
  changelog fragment renamed to the pull request number) no longer brings back
  the `run-ibmi` / `needs-full-tier` labels after a passed IBM i run. (#139)
- Probes are named after where they act: `qtemp_` (read-only or QTEMP) and
  `lib_` (changes a library). A `lib_` probe runs only through
  `bin/probe --approved <link>`, which checks on GitHub that the link is the
  maintainer's approval comment; the link is stored with the probe result. (#143)
- The Django test runs on IBM i and the offline query corpus use Django's own
  `DEFAULT_AUTO_FIELD` per version (`AutoField` on 5.2, `BigAutoField` from
  6.0 on) instead of `AutoField` everywhere, as Django's reference settings do. (#145)
- `bin/ibmi-cleanup` also finds a test table that a crashed run had renamed:
  a `RENAME TABLE` of a table on the cleanup list updates its entry to the
  new name before the statement runs. (#148)
- An `AlterField` that changes a column to a type Db2 for i cannot convert in
  place (for example text to a date, a number to text, or `DateField` to
  `DateTimeField`) raises `NotSupportedError` before any SQL is sent, with the
  workaround (new field, data migration, remove the old field); see Known
  limitations. (#152)
- CI: a conflict-free rebase over `main` commits that change only the IBM i gate
  (`.github/workflows/ibmi-gate.yml`, `scripts/ibmi_gate.py`) no longer needs a
  new IBM i run. In their own pull request those files still count as "needs
  full tier" for the maintainer's review. The gate workflow's job is now called
  `ibmi-gate-check`. The status it sets, `ibmi-gate`, is unchanged.
  A failure before the gate knows the head still gets an error status, and the
  maintainer can re-evaluate one pull request with `workflow_dispatch` (main
  only; its only input is the pull request number). A rebase may carry the
  run's verification stamps commit along without a new run, and
  `scripts/classify_pr.py`, which decides the gate's verdict, now counts as a
  gate file (needs full tier, flagged for the maintainer's review). (#166)
- Migrations can now drop columns, narrow them and make them `NOT NULL`
  without a system reply list entry: while a migration removes or alters a
  field, the backend suppresses inquiry message CPA32B2 for its own job
  (`QSYS2.OVERRIDE_QAQQINI`, query option `SUPPRESS_INQUIRY_MESSAGES`) and
  turns it back on when the migration is done. A narrowing change that would
  truncate a string or round a number is refused with `DataError` first. New
  option `OPTIONS["suppress_inquiry_messages"]` (default `True`); `False` keeps
  CPA32B2 for migrations too. `RunSQL` and your own cursors keep CPA32B2. (#172)
- `OPTIONS["inquiry_message_reply"]` stays, documented as the fallback for
  systems where `QSYS2.OVERRIDE_QAQQINI` is not allowed: turn
  `suppress_inquiry_messages` off and answer CPA32B2 with a system reply list
  entry. (#180)
- Contributor rule: `.env` and its link in a worktree are never moved, renamed, copied, deleted or re-linked; a throwaway worktree without `.env` rules it out as a cause. `.claude/settings.json` denies those commands. (#192)
- The dev and test tooling (pytest, pytest-django, ruff) is pinned in `uv.lock`; Dependabot proposes updates weekly as one pull request, for releases at least 7 days old. Django and pyodbc stay unpinned in the test sessions. (#193)
- Docs: README's alpha notice lists what works after phase 4 (the schema editor), CLAUDE.md's directory tree and phase list match the repository, and the IBM i notes use the current probe names. (#196)
- `bin/probe qtemp_<topic>` runs the QTEMP probes that have their own entry point (`qtemp_encoding`, `qtemp_locale`, ...) through one nox session, `probe_qtemp`, instead of one session per probe; the unused pytest marker `full` is gone, and `qtemp_check_journal` is now `qtemp_check_constraint_unjournaled`. (#197)
- Pull requests that change the core backend (`schema.py`, `introspection.py`, `compiler.py`, `operations.py`, `features.py`, `expressions.py`, `compat.py`) now need the full own IBM i tier, not only a targeted run. (#199)
- One name per test set, in the docs and the code: offline tests, golden files, replay tests (`nox -s replay`), IBM i tests (`nox -s ibmi`, `tests/ibmi/`), Django suite on IBM i (`scripts/django_suite.sh`), targeted and full IBM i runs (label `needs-full-ibmi-run`), and the status run (`bin/status-run`, was the release run). (#202)
- `scripts/django_suite.sh` checks its arguments with the rules of `scripts/run_django_tests.py` (`--check-only`, on the host, before the PUB400 lock), so they live in one place: a label must be a test module label, and options may come between the labels. (#205)
- The release workflow is removed: the maintainer creates each GitHub release by hand from the signed tag, so nothing runs on a tag push anymore (#94). `scripts/changelog_section.py <version>` prints the release notes. (#207)

### Fixed
- `bin/ibmi-test django <label>...` runs every label, also after one failed,
  and names the failed labels at the end; before, the first failing label
  stopped the rest. (#133)
- SQL that ends in `;` (raw SQL in user code and in Django's tests) no longer
  fails with SQL0104: the cursor removes one trailing `;`, as Django's Oracle
  backend does. (#142)
- An `AlterField` that changes or removes the check of a positive integer
  field (for example `PositiveIntegerField` to `IntegerField`) failed with
  `SQL0199 - Keyword NONE not expected`; it now drops the check (#151). (#155)
- CI classification: a pull request always gets its `run-ibmi` /
  `needs-full-tier` labels, also when a quick second push cancelled the run
  for the first one. The previous head now comes from the last completed
  classification, which the PR comment names, not from the push event;
  without such a comment the whole pull request is classified. The labels
  are set before the comment is updated (#158 got no label). (#159)
- A deferred statement of a migration that fails (for example an index the
  database refuses) now rolls the migration's transaction back. Before, the
  connection stayed inside the transaction, and later statements failed with
  "Attempt to use a closed connection". (#160)
- Foreign key violations (SQL0530, SQL0531, SQL0532) now raise
  `IntegrityError` instead of `DatabaseError`: Db2 for i reports them with
  the generic SQLSTATE `HY000`, so they are classified by SQLCODE, as CHECK
  violations are. This matters for foreign key constraints that exist in the
  database already, such as on tables not managed by Django migrations. (#163)
- A CHECK constraint that existing rows violate (SQL0544, for example
  `AlterField` to a `PositiveIntegerField` over negative values) now raises
  `IntegrityError` instead of `DatabaseError`. (#163)
- AddField of a NOT NULL field without any default no longer fails with
  SQL0109 ("NOT NULL clause not allowed"). The column is added with the type's
  system default, which is dropped right after. A table that already has rows
  is refused with `IntegrityError` instead of silently giving those rows the
  system default, as on PostgreSQL. In a migration's transaction the table is
  locked during the check. (#164)
- Tooling: stopping a PUB400 run released the PUB400 lock while the run's
  container kept its connection open, so a second job could start. The lock
  now stops the run's container (`docker stop`, then `docker kill` after a
  timeout) before it releases the lock. A new run removes an exited container
  of an earlier run and refuses to start while one still runs. (#167)
- Tooling: a stop signal that arrived right after the PUB400 lock was taken,
  before the run started, ended the lock process without its container
  cleanup. The lock now handles signals from the moment it holds the lock. A
  signal before the start skips the run, and the container check still runs
  before the lock is released. (#169)
- A column default containing `%` (`default` or `db_default`) was stored
  with the `%` doubled when a migration created the table or added the
  column (`DEFAULT '100%%'` for `"100%"`), and a one-character default `"%"`
  failed with SQL0574. `sqlmigrate` showed the doubled `%` too. Changing a
  default with `AlterField` was not affected. (#183)
- Each git worktree gets its own nox virtualenvs (a Docker volume per checkout), so `bin/check` and other nox runs in two worktrees no longer break each other; `bin/worktree-remove` removes the volume. (#194)
- The test runner accepts a test library journaled with `STRJRNLIB` (new objects inheriting journaling, to an active journal), the same rule as the system check `django_db2_for_i.W001`; before, it accepted only a `QSQJRN` journal in the library. (#205)
- The replay tests are counted per corpus entry again in the test status (since the test set rename they were counted per pytest test, 8 per Django version). (#209)
- `bin/release-prepare` no longer refuses its own staged release files, and runs `bin/check` before it regenerates the status pages, so their offline and replay rows come from a fresh run. (#209)

### Known limitations
- Known limitations: SQL0910 in a migration only hits a column that really
  holds NULLs (verified), or rows changed by `RunPython`/`RunSQL` before a
  schema change of the same table. The workaround is stated plainly:
  `atomic = False`, or a separate data migration before the schema change. (#175)
- `db_index=True` on a `TextField` or `BinaryField` no longer fails with
  SQL0350: Db2 for i cannot index a LOB column, so the index is skipped, as
  Django's Oracle and MySQL backends do. (#176)
- A `CheckConstraint` that matches a column against a pattern built from
  another column (for example `~Q(surname__startswith=F("name"))`) is
  refused by Db2 for i (SQL0546); patterns with a constant work. See Known
  Limitations. (#184)
- Known limitations: `GeneratedField`, `db_collation` and `CharField` without `max_length` are not available on Db2 for i (verified on IBM i 7.5), and `inspectdb` lists no materialized query tables. Every feature flag that was "later" now names phase 5, phase 6, "needs probe" or why it is off. (#198)

## [0.1.0a4] - 2026-10-21

### Added
- Django 6.0 support (6.0.3 or later), next to 6.1. Out-of-range
  `DurationField` values raise the same `ValueError` on both versions. (#110)
- Django 5.2 LTS support (5.2.12 or later), next to 6.0 and 6.1. `StringAgg`
  requires Django 6.0 or later (see Known limitations). (#117)

### Changed
- README redesign: one badge per IBM i, Python and Django version with its
  state, a "Test status" section per Django version over four named test sets
  (Offline · own tests, IBM i · own tests, IBM i · Django test suite,
  Offline · Django test suite (replay)), and the project status with the
  current phase's steps. New reference pages: `docs/FEATURES.md` (the feature
  flags per Django version) and `docs/OFFLINE_CORPUS.md`. (#120)

### Fixed
- A filter value that does not fit its column raised a driver error ("Numeric
  value out of range", "Character data right truncation"): an integer out of a
  `SmallIntegerField`'s (or `IntegerField`'s, `BigIntegerField`'s) range in
  `__in` or `__range`, or a `Decimal` with more digits than `max_digits` /
  `decimal_places` in any lookup. Such values now get a `DECIMAL` type of their
  own and are compared exactly, never rounded or truncated; values that fit
  keep their SQL. Values needing more than 63 digits raise `NotSupportedError`. (#97)
- A CHECK constraint violation (SQL0545, e.g. a negative value in a
  `PositiveIntegerField`) raised `DatabaseError` because the driver reports
  the generic SQLSTATE `HY000`; it now raises `IntegrityError`, like the other
  constraint violations. (#106)

## [0.1.0a3] - 2026-10-20

### Added
- `regex` and `iregex` lookups, as the `REGEXP_LIKE` predicate (ICU regular
  expressions, the database's dialect as on other backends; see
  docs/user/Known-Limitations.md). The pattern is sent as a typed
  `NVARCHAR(16370)` marker. (#29)
- Offline and pub400 guards that no comparison is emitted with untyped
  parameter markers on both sides (Db2 for i compares those wrongly,
  silently). (#35)
- `StringAgg`, as `LISTAGG` of an NCLOB with a typed separator: results up
  to 1M characters (longer fails with SQL0802), NULL over no values (the
  ODBC driver would return an empty string). See
  docs/user/Known-Limitations.md. (#38)
- Truncating dates, times and timestamps: `Trunc()` and its subclasses,
  `TruncDate()` / `TruncTime()`, the `__date` / `__time` lookups and
  `dates()` / `datetimes()`, with `TRUNC_TIMESTAMP` (weeks start on Monday).
  They follow the time zone rule of the date functions (see
  docs/user/Known-Limitations.md). (#44)
- README badges (supported versions, license, offline CI, latest release, and
  the passed / failed / skipped / expected-failure counts of the last Django
  test runs on PUB400) with an explanation of what they mean, and a "Project
  status" section (releases, phases, phase 2 modules, open tracks).
  `scripts/update_test_status.py` (`nox -s test_status`) now also writes the
  shields.io endpoint files in `docs/badges/` and renders the README status
  between marker comments from `docs/status.toml` and the test logs. (#49)
- Durations: `timedelta` values (typed as BIGINT microseconds) and
  `DurationField` arithmetic with dates, times and datetimes
  (`F("start") + F("length")`), exact over the whole timestamp range through
  `DAYS` + `MICROSECONDS` labeled durations (a single `MICROSECONDS` duration
  silently gives NULL from about 31.7 years on). See
  docs/user/Known-Limitations.md. (#56)

### Enabled features
- `supports_regex_backreferencing`. (#29)
- `supports_boolean_expr_in_select_clause`: predicates in the select list
  and GROUP BY are returned as BOOLEAN values. (#31)
- `supports_any_value`: the `AnyValue` aggregate (`ANY_VALUE`). (#39)
- `supports_subqueries_in_group_by`: subquery annotations next to aggregates
  and grouping by a subquery (not yet by one that filters with a value). (#40)
- `supports_select_union`: `union()` querysets. An ordered union is written as
  `SELECT * FROM LATERAL (<union>) ORDER BY ...` (Db2 for i accepts no
  expressions, such as the NULL ordering emulation, in the ORDER BY of a
  union; LATERAL keeps outer references of a correlated subquery visible). (#42)
- `supports_aggregate_order_by_clause`: `StringAgg(..., order_by=...)`, as
  `LISTAGG(...) WITHIN GROUP (ORDER BY ...)`, also with `nulls_first` /
  `nulls_last`. (#43)
- `supports_temporal_subtraction`: subtracting dates, times and datetimes
  (`F("end") - F("start")`) gives a duration, computed in exact microseconds
  with `DAYS()`, `MIDNIGHT_SECONDS()` and `MICROSECOND()` (never
  `TIMESTAMPDIFF`, which assumes 30-day months). The duration skips are gone. (#59)
- `nulls_order_largest`: Db2 for i sorts NULL as the largest value (last
  ascending, first descending); `nulls_first` / `nulls_last` still override it. (#68)
- `supports_select_intersection` and `supports_select_difference`:
  `intersection()` and `difference()` querysets (INTERSECT / EXCEPT). (#72)
- `allow_sliced_subqueries_with_in`: a sliced queryset in an `__in` filter
  (`IN (SELECT ... OFFSET ... FETCH FIRST n ROWS ONLY)`), also in XOR and in
  deletes. (#77)
- `supports_tuple_lookups`: lookups on a multi-column relation
  (`ForeignObject`) use row values: `(a, b) = (x, y)` and
  `(a, b) IN (subquery)`. `exclude()` by such a relation now leaves out rows with
  a NULL in one of its columns, as on other backends (it returned them before).
  IN lists and `>`, `>=`, `<`, `<=` keep the expanded form, which Db2 for i
  needs. (#78)
- `supports_slicing_ordering_in_compound` and `supports_parentheses_in_compound`:
  the parts of `union()`, `intersection()` and `difference()` can be ordered
  and sliced (`qs1.order_by(...)[:2].union(qs2.order_by(...)[:2])`), also when
  the compound query is a subquery (`filter(pk__in=<union of sliced parts>)`),
  and compound queries can be nested. (#80)

### Changed
- The Django test badges name their Python × Django combination and system
  (for example `Django 6.1 · Python 3.14 on PUB400`, from a new `# python:`
  line in the test logs), a new badge shows how many of Django's test
  modules have a recorded run, and "What the test badges mean" states what
  is and is not counted. From phase 3 on, each Django version gets its own
  row of test badges. (#64)
- Changelog entries are written as fragments in `changelog.d/`, one per pull
  request, and assembled into `CHANGELOG.md` at release time
  (`scripts/assemble_changelog.py`).

### Fixed
- `Cast(..., CharField())` without `max_length`, and ordering by a `Value`
  with a `CharField` output (which Django wraps in such a cast), cast to
  `NVARCHAR(16370)`; they produced `CAST(... AS None)` (SQL0204). (#25)
- `SELECT DISTINCT` combined with `nulls_first` / `nulls_last` ordering
  failed with SQL0214. Db2 for i has no `NULLS FIRST/LAST`, and Django's
  emulation (`<expr> IS NOT NULL, <expr>`) must be in the select list for
  DISTINCT queries. The backend's compiler (`compiler.py`, now used for all
  queries) selects the predicate and the expression as hidden columns and
  orders by their positions; the hidden columns never appear in results. (#26)
- Logged SQL (`connection.queries`, `CaptureQueriesContext`, the
  `django.db.backends` logger) shows the parameter values filled in
  (`last_executed_query()`), instead of `QUERY = ... - PARAMS = ...`. The
  text is for logging and debugging only; it is never executed. (#30)
- `Exists()` conditions failed in the IBM i host server ("Error in host
  server data stream"): the subquery selected a parameter marker. It now
  selects a literal `1`. (#31)
- `Exists()` outside a WHERE condition (annotations, `Case(When(Exists()))`,
  `order_by()`, grouping) failed with SQL0104: Db2 for i accepts `EXISTS`
  only as a search condition. There it is rendered as
  `((SELECT 1 ... FETCH FIRST 1 ROWS ONLY) IS NOT NULL)`, which also stops
  at the first row; in WHERE it stays `EXISTS (...)`. (#31)
- A predicate compared with another conditional expression
  (`filter(flag=Q(...))`, `annotate(b=LessThan(...)).filter(b=LessThan(...))`,
  `filter(has=Exists(...))` on an Exists annotation) failed with SQL0104:
  Db2 for i rejects a predicate as a comparison operand. Such operands are
  written as `CASE WHEN <predicate> THEN TRUE ELSE FALSE END`; boolean
  columns are not wrapped. (#33)
- A selected `Q` or lookup annotation with a plain value
  (`annotate(b=Q(pages__lt=100))` on a full queryset) failed with SQL0418
  since `supports_boolean_expr_in_select_clause` was enabled: a select-list
  predicate with an untyped parameter marker is not valid. Such predicates
  are written as `CASE WHEN <predicate> THEN TRUE ELSE FALSE END` (still
  BOOLEAN). Grouping by such an annotation stays a known limitation. (#34)
- `Avg` of an integer field returned a truncated integer (Db2 for i's
  `AVG` of INTEGER is an INTEGER); the argument is now cast to DOUBLE when
  the result is a FloatField. `Avg` of a DecimalField stays DECIMAL. (#36)
- An aggregate whose `filter=` matches nothing (e.g. `Q(pk__in=[])`)
  failed with SQL0171 (`COUNT(NULL)`); the NULL is now typed, as
  `COUNT(CAST(NULL AS <argument type>))`. (#37)
- Grouping by an annotation whose SQL contains a value
  (`annotate(b=Q(pages__lt=100)).values("b").annotate(n=Count("id"))`,
  `values(m=Mod("pages", 10))`, a subquery or `Exists()` that filters with a
  value), or by an expression used inside another selected expression, failed
  on Db2 for i (30101 / SQL0122). Such grouped expressions are computed in a
  `LATERAL` derived table and grouped by its columns; other grouping keeps
  its SQL. (#45)
- The `%`, `**`, `bitand()`, `bitor()`, `bitxor()`, `bitleftshift()` and
  `bitrightshift()` operators failed with SQL0104 (Db2 for i has no such
  operators). They are written as `MOD`, `POWER`, `BITAND`, `BITOR`, `BITXOR`
  and exact shifts; `>>` rounds down like Python (-5 >> 1 = -3). (#47)
- Comparing a boolean column with a negated boolean value
  (`filter(flag=~Value(False))`, `filter(flag=F("negated_annotation"))`) failed
  with SQL0199: `NOT <value>` is a predicate, which Db2 for i rejects as an
  operand. It is written as `CASE <value> WHEN TRUE THEN FALSE WHEN FALSE THEN
  TRUE END`, which keeps NULL as NULL. (#48)
- `Value(<uuid>)` (for example `update(id=Value(uuid))` on a UUIDField)
  raised NotSupportedError; it is sent as a typed `CAST(? AS CHAR(32))`
  marker, like UUIDField columns. (#50)
- Negating a nullable boolean (`filter(~F("flag"))`, `annotate(x=~F("flag"))`)
  gave wrong results for NULL: Db2 for i's `NOT <boolean value>` is TRUE when
  the value is NULL, also in WHERE. Such negations are written as `CASE
  <value> WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END` everywhere, so NULL
  stays NULL and NULL rows do not match. (#51)
- A `timedelta` outside the DurationField range (more than 2**63 - 1
  microseconds, e.g. `timedelta.max`) is refused with a clear `ValueError`
  before it is sent, instead of a driver `OverflowError`. Known Limitations
  now spells out that an update whose date/time result passes year 9999 (or
  year 1) writes NULL. (#57)
- A parameterized statement on an IBM i service (a QSYS2 table function or view
  that calls system APIs) failing with SQL0443 left the connection unusable:
  every later statement failed with SQL0519. The driver now marks such a
  connection unusable (the original error is raised; a later SQL0519 explains
  that a new connection is needed), so Django replaces it. The test library
  journal check no longer passes a parameter to `QSYS2.JOURNAL_INFO`. (#60)
- `iexact` returned no rows for values containing `_`, `%` or `\`: the value
  was escaped for LIKE, although `iexact` compares with `UPPER(column) =
  UPPER(value)`. It is now compared as it is (as on PostgreSQL and Oracle). (#63)
- A filter value longer than its column (e.g. `name__in=["nonexistent"]` on a
  `CharField(max_length=10)`, or a value with an emoji that counts as two
  UTF-16 units) failed with CWB0111 ("Input data is too big to fit into
  field"). Such values are sent as typed parameters and simply match nothing;
  they are never truncated. Values longer than 16370 characters raise
  `NotSupportedError`. (#65)
- `bulk_update()` on a ForeignKey or GenericIPAddressField failed with
  NotSupportedError ("Value of type ... with output field ForeignKey"): a
  ForeignKey value now takes its target field's type (recursively, for a key
  to a key; integer, CharField and UUID primary keys), and an IP address is a
  VARCHAR(39). (#66)
- `IN (subquery)` inside Django's XOR emulation (`Q(pk__in=...) ^ Q(...)`) or a
  selected `Q(...__in=<subquery>)` failed with SQL0115: Db2 for i accepts IN
  (subquery) only as a search condition. There it is written as an exact
  three-valued expression of first-row subqueries, also when negated. (#71)
- `delete()` of a queryset filtered by a subquery on its own table (for
  example `Book.objects.filter(pk__in=Book.objects.filter(...).values("pk"))`)
  failed with SQL0115. Django rewrites such a delete as
  `pk IN (SELECT * FROM (...) subquery)` in a new outer query, whose WHERE
  the compiler did not recognise as a search condition: it wrapped the IN in
  `CASE WHEN ... THEN TRUE ELSE FALSE END`, where Db2 for i rejects IN
  (subquery). (#73)
- Filtering a multi-column relation (`ForeignObject`) by a subquery
  (`account__in=<queryset>`) failed with SQL0216: the IN (subquery) rewrite
  from #71 also reached `(a, b) IN (subquery)` in WHERE, and it compared one
  column with a tuple. In WHERE the condition is no longer rewritten; outside a
  search condition (XOR, a selected `Q`) the rewrite now has one column per
  tuple element, and stays exactly three-valued. (#74)
- A string `Value` longer than its field's `max_length` (also a value in a
  lookup on a multi-column relation) was cast to the field's length and failed
  with CWB0111; it now gets a type of its own length, so the comparison matches
  nothing and a selected value comes back whole. Nothing is ever cut short. (#78)
- A nullable `BooleanField` used as a condition matched its NULL rows where it
  should not: `filter(flag=False)`, `exclude(~F("flag"))`, a boolean annotation
  in `filter(...=False)` / `exclude(...=True)`, and a `When(Q(flag=False))`.
  Db2 for i treats NULL as false in `NOT flag`; boolean values used as
  conditions are now compared with `TRUE` / `FALSE` (also index-friendly), and
  the rows match Django on other databases. (#81)
- A condition selected as a value (`annotate(b=Q(...))`, also in `values()`,
  GROUP BY and `update()`) returned `False` where its result is unknown because
  of a NULL; it now returns `None`, as on other backends
  ([#75](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/75)). (#84)

### Known limitations
- A bare `%s` in `RawSQL()` is an untyped parameter marker, which Db2 for i
  rejects in the select list (SQL0418); cast it in the SQL, e.g.
  `RawSQL("CAST(%s AS NVARCHAR(20))", [value])` (see
  docs/user/Known-Limitations.md). (#54)
- A selected value that cannot be converted, or divides by zero (e.g.
  `Cast("text", IntegerField())` on non-numeric text), is NULL on Db2 for i,
  without an error or a driver warning; in filters the same raises SQL0802.
  See docs/user/Known-Limitations.md. (#61)
- Known Limitations now also covers `extra(select=..., select_params=...)`: a
  bare `%s` there is an untyped parameter marker too (SQL0418); cast it, e.g.
  `extra(select={"foo": "CAST(%s AS INTEGER)"}, select_params=(1,))`. (#67)
- An out-of-range integer in an `__in` list, or a `Decimal` with more digits
  than its column, raises a driver error instead of matching nothing (never
  rounded or truncated); planned fix #69. See docs/user/Known-Limitations.md. (#70)

## [0.1.0a2] - 2026-10-18

### Added
- A warning is logged at the first connection when the process locale is not
  UTF-8: the IBM i Access ODBC driver then garbles non-ASCII characters in
  result column names and error messages (data values are not affected).
- Release workflow (`.github/workflows/release.yml`) for signed `v*` tags:
  verifies the tag (annotated, OpenPGP-signed by the maintainer's key, on
  `main`, matching `__version__`, with a CHANGELOG section), builds sdist
  and wheel, runs the offline tier against the installed wheel and publishes
  a GitHub pre-release with both files. No PyPI.
- Probes for the string encoding investigation (`probe_encoding`,
  `probe_job_ccsid`, `probe_locale`); findings in `docs/IBMI_NOTES.md`.

### Changed
- Packaging: the version (`django_db2_for_i.__version__`) is the single
  source of the package version; classifier `Development Status :: 3 -
  Alpha`; project URLs. Alpha releases are published on GitHub only.

### Fixed
- Long strings arrive intact: string parameters of more than 8184 characters
  bound to `NCLOB`, `DBCLOB` or `CLOB` (such as a `TextField`) lost one
  character per 16369 bytes, silently. The cause was pyodbc sending long
  values in chunks of an odd byte size; the pyodbc driver now sets
  `maxwrite`, so values up to the maximum are sent in one piece. The limit
  for string parameters rises from 8184 to 1,048,576 UTF-16 units (the
  capacity of a `TextField` column); longer strings are refused with
  `NotSupportedError`. Bytes have no limit.
- Non-ASCII text in SQL statements is sent as Unicode: statement text and
  string parameters travel as UTF-8 (pyodbc `setencoding("utf-8",
  SQL_CHAR)`, driver keywords `UNICODESQL=1` and `CCSID=1208`, which can no
  longer be overridden). Before, the IBM i Access ODBC driver converted
  statement text to the job CCSID and silently replaced characters outside
  it (`€` in CCSID 273, emoji). `SchemaEditor.quote_value()` writes strings
  as plain `'...'` constants (column defaults keep `UX'...'`).

## [0.1.0a1] - 2026-10-17

Tagged as `v0.1.0a1` on commit `147e3fc`, without a release workflow. The
code under that tag still reports version `0.0.1.dev0`
(`django_db2_for_i.__version__`); the version number was set with 0.1.0a2.
The tag is not moved or recreated.

### Added
- Phase 0: project skeleton.
  - BSD-3-Clause license, contributing guide, README, changelog.
  - `pyproject.toml` (Django 6.1, pyodbc required) and the backend package
    layout as documented stubs.
  - Container environment: `docker/Dockerfile` with `offline` and `full`
    targets (IBM i Access ODBC Driver pinned by version and SHA256),
    `compose.yaml`, devcontainer, `.env.example`.
  - nox sessions `lint`, `offline` (Python 3.12–3.14 × Django 6.1), `pub400`,
    `probe`; pytest tier markers and an offline connection guard.
  - GitHub Actions workflow for the offline tier.
  - Read-only IBM i probes (`reachability`, `connect`, `sysinfo`, `libraries`).
  - Docs: `DECISIONS.md`, `DJANGO_VERSIONS.md`, `IBMI_NOTES.md` with the
    PUB400 findings, `TEST_STATUS.md`.
- Claude Code project settings deny access to `.env`.

- Phase 1: minimal backend for Db2 for IBM i 7.5 and Django 6.1.
  - `DatabaseWrapper` with a driver layer (`drivers/`: interface and pyodbc +
    IBM i Access ODBC Driver; SQL naming, commitment control `*CS`,
    TrueAutoCommit, extended dynamic SQL packages off) and server
    capabilities (`capabilities.py`: detection from the server version,
    profile `"7.5"`, per-capability overrides in `OPTIONS["capabilities"]`).
  - Conservative `DatabaseFeatures`: every optional flag off until Django's
    tests back it; fixed reason strings for skips and expected failures.
  - Type mapping (`NVARCHAR` for `CharField`, `BOOLEAN`, `TIMESTAMP(6)`, identity
    columns `GENERATED BY DEFAULT`), `CREATE`/`DROP TABLE`, literal defaults,
    minimal introspection.
  - Operations: pagination with `OFFSET` / `FETCH FIRST`, `last_insert_id`,
    `USE_TZ` conversion in the database's time zone, `TimeField` without
    microseconds, `sql_flush` with identity restarts outside the transaction,
    case-insensitive lookups, typed parameter markers for `Value`
    expressions, extracting date/time parts.
  - Test databases in an existing, journaled library (`TEST["CREATE_DB"] =
    False`), guarded by a marker table; never `CREATE`/`DROP SCHEMA`.
  - `OPTIONS["inquiry_message_reply"]` (opt-in): the IBM i job's inquiry
    message reply for the connection, restored to the original value at close,
    plus `connection.set_inquiry_message_reply()` /
    `restore_inquiry_message_reply()`. With `"*SYSRPYL"` and an administrator's
    `ADDRPYLE MSGID(CPA32B2) RPY('I')`, `DROP COLUMN` and narrowing column
    changes are allowed; without it such an `ALTER TABLE` raises an
    `OperationalError` that explains the cause and the fix.
  - Safety: passwords never appear in errors, logs, tracebacks or pytest
    reports; string parameters over 8184 UTF-16 units are refused (LOB
    parameters lose characters).
  - Tests: offline golden files for backend-specific SQL (55, all verified on
    IBM i 7.5), pub400 tier, `scripts/runtests.sh` for Django's own test
    suite (dotted labels, at most three per run) and
    `scripts/update_test_status.py`.
  - Probes for IBM i behaviour (journaling, commitment control, SQL features,
    string limits, column defaults, savepoints, extract functions, inquiry
    messages); findings in `docs/IBMI_NOTES.md`.
  - User documentation in `docs/user/`, mirrored to the GitHub wiki.

### Enabled features
- Savepoints (`uses_savepoints`, `can_release_savepoints`): nested `atomic()`
  blocks use `SAVEPOINT ... ON ROLLBACK RETAIN CURSORS`. Django's
  `transactions` tests: 85 passed, 3 skipped, no failures.

### Fixed
- Date and datetime lookups and `Extract()` (`__year`, `__month`, `__day`,
  `__week_day`, `__iso_week_day`, `__week`, `__quarter`, `__iso_year`,
  `__hour`, `__minute`, `__second`) are implemented. They run in the
  database's time zone; another current time zone raises `NotSupportedError`
  (see docs/user/Known-Limitations.md).
- Column defaults (`db_default`, and Python defaults when a migration adds a
  NOT NULL column) are written as bare literals with one rule per type;
  `CAST(...)` in a DEFAULT was rejected (SQL0574). Strings with quotes or
  non-ASCII characters use `UX'...'` constants, because Db2 for i stores
  escaped quotes in DEFAULT constants wrongly. Unsupported values raise
  `NotSupportedError`.

[Unreleased]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0b1...HEAD
[0.1.0b1]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a4...v0.1.0b1
[0.1.0a4]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a3...v0.1.0a4
[0.1.0a3]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a2...v0.1.0a3
[0.1.0a2]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/releases/tag/v0.1.0a1
