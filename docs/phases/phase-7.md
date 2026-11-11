# Phase 7: Polish and beta 4

> Status: In progress. Approved by the maintainer on 2026-11-11 (the merge of
> [#242](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/242)).

## Goal
Make what runs on PUB400 complete and clean, and release it as **beta 4**
(`0.1.0b4`, GitHub only). **1.0.0 follows after beta 4** (section 11). Since #234
and #236 PUB400 allows up to three connections for lock and concurrency tests, so
the two-connection work that phase 8 held (row locks, `MERGE` under concurrency,
`LOCK TABLE`) belongs here; phase 8 keeps what really needs a dedicated IBM i
([phase-8.md](phase-8.md)).

It replaces the one-line phase 7 of CLAUDE.md ("PUB400 tier & release prep:
curated smoke set, golden verification job, README, packaging") and adds a review
of everything that is still off, skipped or an expected failure, the open
issues, IBM i system names (the 10-character names) set from Django, the row locks
of `select_for_update()`, and Python 3.15.

"Done when":
- Every expected failure, skip and flag that is off has been reviewed, and each one
  is either fixed, or kept with a reason that says it is a Db2 for i limit, a
  Django test that cannot pass on any backend like this one, or phase 8 work.
  The review is recorded in this file (the tables below, filled in).
- `select_for_update()` is on (5 of its 6 flags, `nowait` stays off) with own
  two-connection tests, and `select_for_update` is a supported module.
- System names can be set for tables, columns and indexes (section 6).
- The open issues are closed, or moved to phase 8 with a reason.
- Every "not verified on IBM i" reason in [features.toml](../features.toml) is
  verified by a probe, or the flag is turned on.
- One status run on 6.1, 6.0 and 5.2 with the backend unchanged since, and
  `v0.1.0b4` tagged by the maintainer.

## 1. Where it stands (after phase 6, #239–#241)
- **Supported modules:** 19 Django test modules (with `queries` as 10 labels and
  `model_fields.test_jsonfield`), 0 failures and 0 errors on 6.1, 6.0 and 5.2.
- **Feature flags:** 66 on, 56 intentionally off with a reason (`nowait` since
  #237), 6 planned for this phase (5 row-lock flags and
  `test_db_allows_multiple_connections`), 17 not applicable
  ([FEATURES.md](../FEATURES.md)).
- **Expected failures:** 22 fixed reasons, 88 test ids in `features.py` (a few differ
  per Django version); **skips:** 3 reasons, 11 tests
  ([TEST_STATUS](../TEST_STATUS.md#expected-failures-and-skips-per-reason)).
- **Own IBM i tests:** 416 on 6.1 (plus the 4 two-connection tests of #241).
- **Two connections on PUB400** (#234–#240): four at once worked; the rule is at
  most three, the extra ones only for lock and concurrency tests. Verified with two
  jobs: the row locks (`lib_select_for_update`, #237), `MERGE` under concurrency
  (`lib_merge_concurrency`, #238), `LOCK TABLE` (#162: the driver's commit kept the
  lock; fixed in #241).
- **Open issues:** #82, #95, #124, #233 (Python 3.15); #162, #237, #238 are done
  and closed (their probes ran; #162's fix is #241).

## 2. The review of expected failures
Each reason gets one of three verdicts: **fix** (a backend change can make the
tests pass), **keep** (a Db2 for i limit or a test that checks text only another
backend writes), or **phase 8**. With the maintainer's answers:

| Reason (short) | Tests | Verdict | How |
|---|---|---|---|
| No column rename on IBM i 7.5 / 7.6 | 27 + 3 skips | **keep** (answer 2) | A Known Limitation for 1.0: a table rebuild on IBM i also risks journaling, authorities, triggers and the logical files and views of other programs. Possibly later in 1.x. |
| A column type cannot change in place (SQL0190) | 10 | **keep** | Needs the same rebuild or the missing column rename. |
| `bulk_create(update_conflicts=True)` sets no keys (MERGE returns no rows) | 7 | **keep** (answer 4) | A limitation, as now. |
| Pending row changes before `ALTER TABLE` (SQL0910) | 7 | **analyse** | `null=True` to `null=False` with a default: the `UPDATE` and the `ALTER` in one transaction. Could commit in between when not in an outer `atomic()`; check what Django's tests expect. |
| Time zone conversion in SQL | 5 | **phase 8** | No time zone database on Db2 for i; a time zone table in a library, only if a user needs it. |
| Test counts the word `EXTRACT` | 6 | **keep** | The test checks another backend's SQL text. |
| `TIME` has no fractional seconds | 4 | **keep** | A Db2 for i type limit. |
| Untyped NULL as an expression (SQL0206) | 1 | **fix** | With #82; cast `NULL` where the type is known. |
| A bare `%s` in `RawSQL` / `extra()` | 3 | **keep** | The user's SQL; documented. |
| `CHR` / `ASCII` single-byte | 2 | **analyse** | A QTEMP probe of a graphic conversion (`UX'...'`, `GRAPHIC` / `VARGRAPHIC` of a UTF-16 code unit) for `Chr`; `Ord` through `HEX` of the UTF-16 value. |
| JSON: no `CHECK`, no function in an index or a `CHECK`, keys with `"`, ordering as text | 1 + 3 + 2 + 1 | **keep** | Db2 for i limits (probes `lib_json_check`, `json_lookups`). |
| `CHECK` with `LIKE` on a column pattern | 2 | **keep** | Db2 for i limit (SQL0546). |
| Typed markers compare wrongly | 1 | **analyse** | Check whether it is still needed after phase 6. |
| Unknown `Trunc` kind, identity restart in `TestCase`, `RETURNING` and lowercase names in the SQL text | 2 + 1 + 2 + 1 | **keep** | The tests check text or behaviour of other backends. |

## 3. Skips, flags that are off, and the two-connection work
**Skips** (11): `REVERSE`, `HASH_SHA224`, `HASH_SHA384` do not exist (keep); the 3
column-rename skips (keep, see above); the Trunc NULL test on 6.0 and 5.2 (keep
until 5.2 and 6.0 are dropped).

**`select_for_update()`** (moved from phase 8; based on `lib_select_for_update`,
#237, [IBMI_NOTES](../IBMI_NOTES.md#two-jobs-row-locks-lock-table-merge-lib_select_for_update-lib_lock_table-lib_merge_concurrency)):
- The SQL is `FOR UPDATE ... WITH RS`: a plain `FOR UPDATE` locks nothing once
  Django has fetched the rows under `*CS`.
- On: `has_select_for_update`, `has_select_for_update_skip_locked`
  (`SKIP LOCKED DATA`), `has_select_for_update_of` with `select_for_update_of_column`
  (`FOR UPDATE OF <column> WITH RS`), `supports_select_for_update_with_limit`
  (`FETCH FIRST` locks only those rows). A join locks the rows of every table in
  it, and `FOR UPDATE` is refused with a join (SQL0511): `of=` on a join needs the
  `WITH RS USE AND KEEP EXCLUSIVE LOCKS` form or stays a limitation (decided by
  Django's tests).
- **`has_select_for_update_nowait` stays off:** Db2 for i has no per-statement
  no-wait (`NOWAIT`, `WAIT 0`, `SET CURRENT LOCK TIMEOUT`: SQL0104).
- Own IBM i tests with two connections (lock, wait, skip, `of=`, a slice), and
  `select_for_update` as a supported module.

**Done with two connections:** `MERGE` under concurrency (#238: `ignore_conflicts`
skips another job's uncommitted row without waiting, now in Known Limitations;
`update_conflicts` waits); `LOCK TABLE` (#162: fixed in #241, the table is free
after the migration's commit or rollback).

**`test_db_allows_multiple_connections`** (moved from phase 8): it needs only a
second connection to the same test library, not `CREATE SCHEMA` (that is
`can_clone_databases`, phase 8). On (answer 6): only the specific Django tests that
need more connections than PUB400's rule allows are skipped, with that reason, and
listed exactly here and in [phase 8](phase-8.md) to be unskipped on a dedicated IBM
i. Our own tests stay within the limit.

**The LOB limit for 3 or more LOB columns and `MERGE`** (moved from phase 8): a
measurement with one connection, a QTEMP probe (`qtemp_bulk_lobs`, as
`qtemp_bulk_types` measured 1 and 2 columns): bisect 3 and 5 `NCLOB` columns and a
`MERGE`, then adjust `bulk_batch_size()` if the limit allows larger batches.

**Foreign keys across differently journaled libraries** (moved from phase 8):
`default` and `other` each have their own `QSQJRN` journal (IBMI_NOTES, journal
setup 2026-10-16 and 2026-10-17), so a `lib_` probe on PUB400 can test
`DB_CASCADE` / `DB_SET_NULL` across them inside a transaction; an approval request
first (open question 3).

**Flags off "not verified on IBM i"**: a QTEMP probe each, then on, or the reason
gets its probe: `allows_group_by_selected_pks`, `greatest_least_ignores_nulls`,
`has_case_insensitive_like`, `has_native_json_field`, `has_native_uuid_field`,
`supports_explaining_query_execution`, `supports_logical_xor`,
`supports_tablespaces`, `supports_uuid4_function`, `supports_uuid7_function`. Most
are expected to stay off; `allows_group_by_selected_pks` and a UUID function are
worth a real look.

**Flags off by design** (Db2 for i limits with a probe behind them): no review
beyond checking that each reason still holds on the newest PTF level PUB400 has.

**Still phase 8:** `can_clone_databases` (a schema per test process).

## 4. The open issues
| Issue | Proposal |
|---|---|
| [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82) `annotations` / `expressions_case` | Run both modules, fix what is the backend's (untyped NULL, `FullResultSet` with a grouped predicate, bytes `Value`), make them supported modules. |
| [#95](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/95) `Value(Decimal)` with more digits than its field | Decide the rule (round, refuse, or widen the cast), fix, own IBM i test. |
| [#124](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/124) tables in another library than `NAME` | Qualified constraint and index names. Possible on PUB400 with the second library (`other`); a `lib_` probe of its own, with its own approval request (answer 8). |
| [#233](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/233) Python 3.15 | Section 8. |
| [#162](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/162), [#237](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/237), [#238](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/238) | Done (probes run, results in IBMI_NOTES); #162 with the fix [#241](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/241). Closed 2026-11-11. |

Checked: [#154](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/154)
(`test_probes.py` on its own) and the STRJRNLIB issue
[#156](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/156)
(fixed in #205) are closed.

## 5. More supported modules
The maintainer's list (answer 3): `delete`, `update`, `annotations`,
`expressions_case` (#82), `select_related`, `prefetch_related`, `many_to_many`,
`get_or_create`, `dates`, `datetimes`, `timezones`, and `select_for_update`
(section 3). Not the whole `model_fields`. Each is measured once on 6.1, fixed or
kept with reasons, then joins `docs/status.toml`'s list (one run per version in
every status run).

## 6. IBM i system names (10 characters)
Every table, column and index on IBM i has, next to its SQL name (up to 128
characters), a **system name** of at most 10 characters: the name RPG and CL
programs, `DSPFD`, `WRKOBJ`, journals and most IBM i tools use (and CL commands
need: `CHGPF` refused the SQL name, CPD0074, #237). Today the backend never sets
one, so IBM i generates it (`TESTAPP_AUTHOR` becomes something like `TESTA00001`).
A must for this phase (answer 5).

**The SQL** (every form verified by a QTEMP probe first, `qtemp_system_names`; not
IBM's documentation alone):
- tables: `CREATE TABLE <sql name> FOR SYSTEM NAME <sys> (...)`;
  `RENAME TABLE ... TO <name> FOR SYSTEM NAME <sys>`;
- columns: `<sql name> FOR COLUMN <sys> <type>`, in `CREATE TABLE` and in
  `ALTER TABLE ... ADD COLUMN`;
- indexes: `CREATE INDEX ... FOR SYSTEM NAME`, and on `RENAME INDEX`, if the probe
  shows Db2 for i accepts them;
- constraints have no system name: out of scope.

**Configuration** (answer 5: options A and C):
- **A.** A mapping in `DATABASES[...]["OPTIONS"]["system_names"]`, keyed by
  `db_table` and by column (and index name), which works with historical models in
  migrations and with apps you do not own (`auth`, `contenttypes`).
- **C.** A `db_table` / `db_column` of at most 10 valid characters *is* the system
  name, as today.
- Two objects that map to the same system name are refused before the `CREATE`.

**Introspection** reads `QSYS2.SYSTABLES.SYSTEM_TABLE_NAME`,
`SYSCOLUMNS.SYSTEM_COLUMN_NAME` and `SYSINDEXES.SYSTEM_INDEX_NAME`; `inspectdb`
writes the system names it finds (as `db_table` / `db_column` when there is no
long name, as a suggested mapping otherwise). Goldens for every new SQL shape, own
IBM i tests (create, add column, rename, introspection, the duplicate refusal).

## 7. The original phase 7 items
- **A smoke set** (`nox -s smoke`), **before beta 4** (answer 9): a selection of
  about 30 existing own IBM i tests of the most common patterns plus a nox session,
  minutes instead of hours, for a user (and the maintainer, trying beta 4 on another
  IBM i) to check their own IBM i after installing.
- **The golden verification job:** done in practice (`bin/verify`, the stamps, the
  CI gate). Only documentation left.
- **README and user docs:** a review from the point of view of a first-time user;
  an upgrade note from the betas.

## 8. Python 3.15 (#233)
pyodbc 5.5.0 has `cp315` wheels (manylinux and musllinux, x86_64 and aarch64), and
Django supports Python 3.15 from **6.1.3** (6.0 and 5.2 do not). So, officially
supported: **3.15 × Django 6.1 (6.1.3 or newer)**:
- the image gets 3.15 (`docker/Dockerfile`), the nox matrix adds 3.15 to 6.1 only,
  the `pyproject.toml` classifier, `docs/DJANGO_VERSIONS.md` (per Django version
  its Pythons, with the 6.1.3 release notes), README and `docs/user/Installation.md`;
- the minimum Django stays as it is for everyone; only Python 3.15 users need
  Django 6.1.3 or newer, through an environment marker next to the normal range
  (`"django>=6.1.3; python_version >= '3.15'"`, answer 7), documented in the README
  and `docs/DJANGO_VERSIONS.md`;
- the image change is "needs full IBM i run": the full own IBM i tests on 3.15 ×
  6.1;
- the matrix rule (CLAUDE.md section 6): the IBM i tests and the status run use the
  **newest Python supported by that Django version** (3.15 for 6.1, 3.14 for 6.0
  and 5.2);
- free-threaded Python (`3.15t`): phase 8 (#233).

## 9. Polishing the workflow
Docs and tooling only, no IBM i runs:
- `bin/check` classifies the uncommitted changes too (today it sees only commits,
  so a change not yet committed shows "docs/tests only").
- `bin/verify` selects the right tests for a change to `tests/corpus/capture.py`.
- The own IBM i tier saves its results as it goes, so an interrupted run (a
  dropped connection, `08S01`) does not lose hours: a rerun continues from the
  last test that finished.
- Core-backend pull requests also run `migrations` and `schema` on 6.1 (the
  after-beta list): a change to `scripts/classify_pr.py` / `scripts/verify.py`.
- The flaky offline test `test_a_killed_holder_releases_the_lock` (it failed once
  under load, 2026-11-04): a longer wait for the lock release.
- TEST_STATUS shows the last run's own IBM i count per version, which is 19 after a
  goldens-only `bin/verify`: count the full tier only, or say which kind of run.
- A push of stamps plus docs after a run fails the IBM i gate (#227): let the gate
  accept stamps followed by docs-only commits, or document "stamps alone".

## 10. Working method and order
As in phase 6: docs and tooling separately and fast, without IBM i runs; the
backend work on **one branch with a commit per step**, targeted runs on 6.1 while
building, **one final cycle** on 6.1, 6.0 and 5.2, then **one status run** for beta
4. New open questions are collected and asked all at once.

| Part | What | IBM i | ETA (PUB400's speed) |
|---|---|---|---|
| 0 | #241 (the `LOCK TABLE` fix): its full run | full own tier on 6.1 | ~5 h, running |
| 1 | Workflow polish (section 9, the three new items first), docs (section 7 docs part), the smoke set (a selection + a nox session; its first run with the next IBM i run) | none (the smoke set: one short run) | 2–3 days of work |
| 2 | Python 3.15 (section 8), its own pull request | full own tier on 3.15 × 6.1 | 1 day + ~5 h run |
| 3 | QTEMP probes: the section 3 flags, `CHR` / `ASCII`, `qtemp_system_names`, `qtemp_bulk_lobs` | QTEMP probes, minutes each | 1–2 days |
| 4 | Two `lib_` probes, each after its own approval: foreign keys across the two journals; #124 (a table in `other`) | two probes | 1 day |
| 5 | The backend branch, a commit per step: `select_for_update`; `test_db_allows_multiple_connections`; system names; #82 / #95 and the **fix** verdicts; the LOB batch size; the extra modules measured and fixed | targeted runs on 6.1 (a module: 10–60 min; the own tier: ~5 h) | 2–3 weeks |
| 6 | The final cycle: supported modules + own tier on 6.1, 6.0, 5.2 | ~1 day per version | 3–4 days |
| 7 | The status run, then `bin/release-prepare 0.1.0b4` | ~1–2 days per version | 4–6 days |

About 4–6 weeks in total, most of it PUB400 time; parts 1–4 run while part 5's
targeted runs wait.

## 11. Releases: beta 4, then 1.0.0
- **Beta 4** (`0.1.0b4`) at the end of this phase, on GitHub only, as the betas
  before it: `bin/release-prepare`, the maintainer merges, tags and releases.
- **1.0.0** after beta 4: the preconditions (a complete status run with the backend
  unchanged since; no open issue labelled `bug`; the user docs reviewed;
  CHANGELOG assembled), then `bin/release-prepare 1.0.0` and the maintainer's tag.
- **PyPI** (answer 1): not for beta 4. Decided at 1.0.0; if yes, a trusted
  publisher (GitHub OIDC) in a protected environment that needs the maintainer's
  manual approval for each release. Claude never publishes.
- **What 1.0.0 promises:** semantic versioning from then on, and the supported IBM
  i releases and Django versions (7.5 and up; Django 5.2, 6.0, 6.1; 6.2 LTS in a
  1.x release). 1.0.0 does not wait for phase 8: the Known Limitations say what
  was not verified on a dedicated IBM i.

## Answers (maintainer, 2026-11-11)
1. PyPI: not for beta 4; decided at 1.0.0 (section 11).
2. Column-rename table rebuild: no; a Known Limitation for 1.0, possibly later in 1.x.
3. Extra modules: the list in section 5.
4. `update_conflicts` keys: keep as a limitation.
5. System names: a must; options A and C, `FOR SYSTEM NAME` / `FOR COLUMN` (and
   for indexes if the probe allows), introspection and `inspectdb`, the duplicate
   refusal; constraints out of scope; every form verified by the QTEMP probe.
6. `test_db_allows_multiple_connections`: on; only the specific tests that need more
   connections than PUB400's rule allows are skipped with that reason, listed
   exactly, and marked in phase 8 to be unskipped there; our own tests stay within
   the limit.
7. Python 3.15: an environment marker (`django>=6.1.3; python_version >= '3.15'`),
   documented in the README and DJANGO_VERSIONS; the minimum is not raised for
   everyone.
8. Foreign keys across the two journals and #124: two separate `lib_` probes, each
   with its own approval request.
9. The smoke set: before beta 4.

## Open questions
None at the moment; new ones are collected and asked all at once.

## Links
- [phase-8.md](phase-8.md): what needs a dedicated IBM i.
- [FEATURES.md](../FEATURES.md), [TEST_STATUS.md](../TEST_STATUS.md),
  [Known limitations](../user/Known-Limitations.md), [IBMI_NOTES.md](../IBMI_NOTES.md).
