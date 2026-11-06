# Phase 7: Polish and release 1.0.0

> Status: Proposed, not yet approved. Nothing in it starts before
> approval (CLAUDE.md: plan before code).

## Goal
Make what runs on PUB400 complete and clean, then release **1.0.0**. Phase 7 is
the last phase that can be done on a shared IBM i; everything that needs a
dedicated IBM i moves to [phase 8](phase-8.md).

It replaces the one-line phase 7 of CLAUDE.md ("PUB400 tier & release prep:
curated smoke set, golden verification job, README, packaging") and adds a review
of everything that is still off, skipped or an expected failure, the open
issues, and IBM i system names (the 10-character names) set from Django.

"Done when" (proposed):
- Every expected failure, skip and flag that is off has been reviewed, and each one
  is either fixed, or kept with a reason that says it is a Db2 for i limit, a
  Django test that cannot pass on any backend like this one, or phase 8 work.
  The review is recorded in this file (the tables below, filled in).
- The open issues are closed, or moved to phase 8 with a reason.
- Every "not verified on IBM i" reason in [features.toml](../features.toml) is
  verified by a QTEMP probe, or the flag is turned on.
- The release preconditions below hold, and `v1.0.0` is tagged by the maintainer.

## 1. Where it stands (after phase 6)
- **Supported modules:** 19 Django test modules (with `queries` as 10 labels and
  `model_fields.test_jsonfield`), 0 failures and 0 errors on 6.1, 6.0 and 5.2.
- **Feature flags:** 66 on, 55 intentionally off with a reason, 6 planned (the
  row locks, phase 8), 17 not applicable ([FEATURES.md](../FEATURES.md)).
- **Expected failures:** 22 fixed reasons, 88 test ids in `features.py` (a few differ per Django version);
  **skips:** 3 reasons, 11 tests ([TEST_STATUS](../TEST_STATUS.md#expected-failures-and-skips-per-reason)).
- **Own IBM i tests:** 416 on 6.1.
- **Open issues:** #82, #95, #124, #162.

## 2. The review of expected failures
Each reason gets one of three verdicts: **fix** (a backend change can make the
tests pass), **keep** (a Db2 for i limit or a test that checks text only another
backend writes), or **phase 8**. A first analysis:

| Reason (short) | Tests | First verdict | How it could be fixed |
|---|---|---|---|
| No column rename on IBM i 7.5 / 7.6 | 27 + 3 skips | **analyse** | Emulate `RENAME COLUMN` with a table rebuild (create the new table, copy, drop, rename), as SQLite's backend does. Large and risky (constraints, indexes, journaling, CPA32B2); the phase 4 decision chose no rebuild. Decide: rebuild, or keep with a Known Limitation. |
| A column type cannot change in place (SQL0190) | 10 | **analyse** | The same table rebuild, or an add-copy-drop-rename of the column (needs the rename that is missing). Depends on the row above. |
| `bulk_create(update_conflicts=True)` sets no keys (MERGE returns no rows) | 7 | **fix?** | Read the keys back with a second `SELECT` on the `unique_fields` after the `MERGE`. Costs a query per batch; the phase 5 decision was "not planned". |
| Pending row changes before `ALTER TABLE` (SQL0910) | 7 | **analyse** | `null=True` to `null=False` with a default: the `UPDATE` and the `ALTER` in one transaction. Could commit in between when not in an outer `atomic()`; check what Django's tests expect. |
| Time zone conversion in SQL | 5 | **keep** (or a big fix) | No time zone database on Db2 for i. A fix would need a time zone table in a library: not on PUB400, so phase 8 if ever. |
| Test counts the word `EXTRACT` | 6 | **keep** | The test checks another backend's SQL text. |
| `TIME` has no fractional seconds | 4 | **keep** | A Db2 for i type limit; storing `TimeField` as `TIMESTAMP` would change the column type for every user. |
| Untyped NULL as an expression (SQL0206) | 1 | **fix?** | Related to #82; cast `NULL` where the type is known. |
| A bare `%s` in `RawSQL` / `extra()` | 3 | **keep** | The user's SQL; documented. |
| `CHR` / `ASCII` single-byte | 2 | **analyse** | Probe a graphic conversion (`UX'...'`, `GRAPHIC`/`VARGRAPHIC` of a UTF-16 code unit) for `Chr`; `Ord` through `HEX` of the UTF-16 value. |
| JSON: no `CHECK`, no function in an index or a `CHECK`, keys with `"`, ordering as text | 1 + 3 + 2 + 1 | **keep** | Db2 for i limits (probes `lib_json_check`, `json_lookups`). |
| `CHECK` with `LIKE` on a column pattern | 2 | **keep** | Db2 for i limit (SQL0546). |
| Typed markers compare wrongly | 1 | **analyse** | Check whether it is still needed after phase 6. |
| Unknown `Trunc` kind, identity restart in `TestCase`, `RETURNING` and lowercase names in the SQL text | 2 + 1 + 2 + 1 | **keep** | The tests check text or behaviour of other backends. |

## 3. The review of skips and flags that are off
**Skips** (11): `REVERSE`, `HASH_SHA224`, `HASH_SHA384` do not exist (keep, unless a
probe finds a way: `SHA224` / `SHA384` cannot be built from `HASH_SHA256` /
`HASH_SHA512`); the 3 column-rename skips (see above); the Trunc NULL test on 6.0
and 5.2 (keep until 5.2 and 6.0 are dropped).

**Flags off "not verified on IBM i"** — a QTEMP probe each, then on, or the reason
gets its probe:
`allows_group_by_selected_pks`, `greatest_least_ignores_nulls`,
`has_case_insensitive_like`, `has_native_json_field`, `has_native_uuid_field`,
`supports_explaining_query_execution`, `supports_logical_xor`,
`supports_tablespaces`, `supports_uuid4_function`, `supports_uuid7_function`.
Most are expected to stay off; `allows_group_by_selected_pks` (Db2 for i accepts
functional dependence on a key in some releases) and a UUID function (from
`GENERATE_UNIQUE()` or `RAND()`) are worth a real look.

**Flags off by design** (Db2 for i limits with a probe behind them): no review
beyond checking that each reason still holds on the newest PTF level PUB400 has.

**Flags that need a dedicated IBM i:** the 6 row-lock flags,
`test_db_allows_multiple_connections`, `can_clone_databases`: phase 8.

## 4. The open issues
| Issue | Proposal |
|---|---|
| [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82) `annotations` / `expressions_case` | Run both modules, fix what is the backend's (untyped NULL, `FullResultSet` with a grouped predicate, bytes `Value`), make them supported modules. |
| [#95](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/95) `Value(Decimal)` with more digits than its field | Decide the rule (round, refuse, or widen the cast), fix, own IBM i test. |
| [#124](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/124) tables in another library than `NAME` | Qualified constraint and index names. Possible on PUB400 with the second library (`other`); a `lib_` probe with approval. |
| [#162](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/162) `lib_lock_table` | Needs two jobs to show what it blocks: phase 8. |

## 5. More supported modules
Django modules not yet supported that a typical project uses, measured once each
on 6.1, then fixed or kept with reasons: `delete` and `update` first (they ran
green in phases 5 and 6, but are not in `docs/status.toml`'s list, so the status
run does not cover them), `annotations`, `expressions_case` (#82), `model_fields`
(whole, measured in phase 6), `select_related`,
`prefetch_related` (window functions now make sliced prefetches possible),
`many_to_many`, `custom_lookups`, `dates`, `datetimes`, `timezones`,
`get_or_create`, `fixtures`, `serializers`. The list is a proposal: each module
costs a run per version in every status run, so it should earn its place.

## 6. IBM i system names (10 characters)
Every table, column, index and constraint on IBM i has, next to its SQL name
(up to 128 characters), a **system name** of at most 10 characters: the name RPG
and CL programs, `DSPFD`, `WRKOBJ`, journals and most IBM i tools use. Today the
backend never sets one, so IBM i generates it: `TESTAPP_AUTHOR` (14 characters)
becomes something like `TESTA00001`, a long index `P24_A00001` (probe 24,
[IBMI_NOTES](../IBMI_NOTES.md)). For a shop where RPG programs read the same
tables, chosen system names matter.

**What Db2 for i offers** (to verify with a QTEMP probe, `qtemp_system_names`):
- `CREATE TABLE <sql name> FOR SYSTEM NAME <sys> (...)`;
- per column `<sql name> FOR COLUMN <sys> <type>`, also in `ALTER TABLE ... ADD COLUMN`;
- `RENAME TABLE ... TO <name> FOR SYSTEM NAME <sys>` (seen in probe 24); `RENAME
  INDEX` the same;
- for an index and a constraint: whether `CREATE INDEX ... FOR SYSTEM NAME` or
  only a short SQL name works (to probe);
- the catalog: `QSYS2.SYSTABLES.SYSTEM_TABLE_NAME`,
  `SYSCOLUMNS.SYSTEM_COLUMN_NAME`, `SYSINDEXES.SYSTEM_INDEX_NAME`, for
  introspection and `inspectdb`.

**The design question: where a Django project writes the name.** Migrations run
with *historical* models, which keep only the fields' constructor arguments and
the `Meta` options Django knows; an attribute of the model class, or an unknown
`Meta` option (Django refuses those), is lost. So the name must live where a
migration keeps it:

| Option | Tables | Columns | Pros / cons |
|---|---|---|---|
| A. A mapping in `DATABASES[...]["OPTIONS"]["system_names"]`, keyed by `db_table` and column | yes | yes | Works with historical models and with apps you do not own (`auth`, `contenttypes`); but the names live outside the models, and a rename in a migration must update the mapping too. |
| B. Backend field classes (`django_db2_for_i.models.CharField(..., system_name="CUSNO")`) whose `deconstruct()` carries the name | no | yes | The name sits next to the field and survives migrations; but every field type needs a subclass, and the models import the backend. |
| C. A convention in `db_table` / `db_column`: a name of at most 10 valid characters *is* the system name (`db_table = "CUSORD"`) | yes | yes | Nothing new to learn and works today; but the SQL name is then the short one too. |
| D. A naming rule in `OPTIONS` (for example the first 10 characters, or a hash suffix) that the backend applies to every object | yes | yes | No per-object work; but the names are not the ones a shop already has. |

A first proposal: **A for tables and columns, C keeps working as it does, B
later only if users ask**; `inspectdb` writes the system names it finds (as
`db_table` for a table with no long name, as a mapping suggestion otherwise).
Also to decide: what happens to a system name when Django renames a table or a
column (a column rename is not possible today, see section 2), and how two
models that map to the same system name are refused before the `CREATE`.

## 7. The original phase 7 items
- **A smoke set** (`nox -s smoke`): about 30 own IBM i tests of the most common
  patterns, minutes instead of hours, for a user to check their own IBM i after
  installing. The full own tier stays for pull requests.
- **The golden verification job:** done in practice (`bin/verify`, the stamps, the
  CI gate). Only documentation left.
- **README and user docs:** a review from the point of view of a first-time user;
  an upgrade note from the betas.
- **Packaging:** see "Release 1.0.0".

## 8. Polishing the workflow
- Core-backend pull requests also run `migrations` and `schema` on 6.1 (the
  after-beta list): a change to `scripts/classify_pr.py` / `scripts/verify.py`.
- The flaky offline test `test_a_killed_holder_releases_the_lock` (it failed once
  under load, 2026-11-04): a longer wait for the lock release.
- TEST_STATUS shows the last run's own IBM i count per version, which is 19 after a
  goldens-only `bin/verify`: count the full tier only, or say which kind of run.
- A push of stamps plus docs after a run fails the IBM i gate (#227): let the gate
  accept stamps followed by docs-only commits, or document "stamps alone".

## 9. Release 1.0.0
Preconditions (proposed): this phase done; a complete status run on all three
Django versions with the backend unchanged since; no open issue labelled `bug`;
CHANGELOG assembled; the user docs reviewed. Then `bin/release-prepare 1.0.0` and
the maintainer's tag, as for the betas.

Decisions for the maintainer:
- **Where 1.0.0 is published.** Today releases are on GitHub only, no PyPI
  (CONTRIBUTING, "Releases"). Publishing on PyPI needs a PyPI project, a trusted
  publisher (GitHub OIDC) or a token, and a release workflow, which #94 removed.
- **What 1.0.0 promises:** semantic versioning from then on (settings and
  behaviour change only in a major release), and which IBM i releases and Django
  versions it supports (7.5 and up; Django 5.2, 6.0, 6.1; 6.2 LTS in a 1.x
  release).
- **Whether 1.0.0 waits for phase 8.** Proposed: no; the Known Limitations say
  what was not verified on a dedicated IBM i, and phase 8 follows in 1.x releases.

## 10. Proposed pull requests
By risk, each with its own IBM i run as the classification asks (or bundled, as in
phase 6, if PUB400 stays slow):
1. The QTEMP probes of section 3 and the `CHR` / `ASCII` probe; the analysis of
   the column-rename rebuild (a decision record, no code).
2. Issues #82 and #95, with `annotations` and `expressions_case` as modules.
3. Expected-failure fixes that the review marks **fix**.
4. #124 (with its `lib_` probe approval).
5. System names (section 6): the probe, the design decision, then the schema
   editor, introspection and `inspectdb`, with goldens and own IBM i tests.
6. More supported modules (section 5).
7. Workflow polish (section 8) and the smoke set.
8. Docs review, then the release pull request for 1.0.0.

## Open questions
1. PyPI for 1.0.0, or GitHub only as for the betas?
2. The column-rename table rebuild: worth it for 1.0.0, or a Known Limitation?
3. Which extra modules (section 5) belong in the supported set?
4. The `update_conflicts` keys (second query): fix now, or keep as a limitation?
5. System names: which of the options A to D (section 6), and must the names of
   indexes and constraints be settable too, or only tables and columns?

## Links
- [phase-8.md](phase-8.md): what needs a dedicated IBM i.
- [FEATURES.md](../FEATURES.md), [TEST_STATUS.md](../TEST_STATUS.md),
  [Known limitations](../user/Known-Limitations.md), [IBMI_NOTES.md](../IBMI_NOTES.md).
