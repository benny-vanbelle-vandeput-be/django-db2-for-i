# Phase 8: On a dedicated IBM i

> Status: Proposed, not yet approved. It starts when a dedicated IBM
> i is available; nothing in it can run on PUB400.

## Goal
Verify and enable what a shared system cannot show: anything that needs two
connections, changes outside the two test libraries, system values or reply list
entries, more than one Db2 for i release or PTF level, or the full Django test
suite. Releases 1.x after 1.0.0 ([phase 7](phase-7.md)).

"Done when" (proposed): every item below is verified on the dedicated IBM i and
either enabled (with an own IBM i test) or documented as a limit with its probe;
the open tracks in `docs/status.toml` that name a dedicated IBM i are closed.

## 1. What the system needs
- IBM i 7.5 (the minimum and primary target), ideally also 7.6, and 7.4 if it is
  ever added (section 6).
- A user profile that may `CREATE SCHEMA` (two schemas of at most 10 characters,
  such as `DJTEST` and `DJTESTOTH`, CLAUDE.md section 6), and the authority to
  change the system reply list or a QAQQINI in its own library, for the CPA32B2
  cases.
- Several concurrent connections from the test machine (PUB400 allows one).
- Readable TR and Db2 PTF Group levels (`QSYS2.GROUP_PTF_INFO`), which PUB400 hides.
- No other users' load, so that timings and the full suite are repeatable.

## 2. Two connections: locks and concurrency
| Item | Today | Approach |
|---|---|---|
| **`select_for_update()`** (6 flags, phase 6 decision 1) | off; syntax probed only (`qtemp_select_for_update`) | `lib_select_for_update`: job A locks rows (`FOR UPDATE`, `WITH RS USE AND KEEP EXCLUSIVE LOCKS`), job B tries to read, update, skip (`SKIP LOCKED DATA`) and wait (`WAIT`, lock wait time). Then the flags, `select_for_update` as a supported module, and own tests with two connections. Note `FOR UPDATE` is refused with a join, `DISTINCT`, `GROUP BY`, `UNION` (SQL0511): `select_for_update(of=...)` and `supports_select_for_update_with_limit` may need the `WITH RS` form. |
| **`MERGE` under concurrency** (`lib_merge_concurrency`) | documented from IBM's docs, not verified | Two jobs insert the same key through `bulk_create(ignore_conflicts=True)` / `update_conflicts` / `m2m.add()`; record which one fails and how (SQL0803), under `*CS` and the isolation levels Django uses. |
| **`LOCK TABLE`** (#162, `lib_lock_table`) | approval request open | Two jobs: what `LOCK TABLE ... IN EXCLUSIVE MODE` lets the other read or change. |
| **`test_db_allows_multiple_connections`**, **`can_clone_databases`** | off | Django's parallel test runner: a schema per process (`CREATE SCHEMA`), then `--parallel` greater than 1 for the full suite. |

## 3. Creating test schemas
Today tests run in two pre-existing libraries ("use existing schema" mode,
phase 1). With `CREATE SCHEMA` authority: the normal Django mode (create and drop
the test database), journaled automatically, with the existing mode kept for
shared systems. Configuration (`TEST`), docs and own tests for both modes.

## 4. The full Django suite (tier 3)
CLAUDE.md section 6: the source of truth for the flags is Django's whole suite on a
dedicated IBM i, never on PUB400. Approach: `settings_django_suite.py` for the
dedicated schemas, a run of all modules per Django version (with `--parallel`
after section 2), and a triage of every failing module into: backend bug (fix),
Db2 for i limit (reason), not applicable (GIS, PostgreSQL-only). TEST_STATUS then
reports the whole suite next to the supported modules.

## 5. Things a shared system hides
| Item | Approach |
|---|---|
| **CPA32B2 with a system reply list entry** | Verify the behaviour with an `*SYSRPYL` entry instead of the per-job QAQQINI override; the unverifiable goldens mechanism is ready for it (`tests/offline/golden/unverifiable.toml`). |
| **Foreign keys across differently journaled libraries** (phase 6) | `lib_on_delete` with two libraries and two journals: `DB_CASCADE` / `DB_SET_NULL` across them, inside a transaction. |
| **The LOB limit of a multi-row statement with 3 or more LOB columns** (phase 5 track) | Measure where the limit lies (between 1,024 and 1,056 markers for 1 and 2 columns), for 3 and 5 columns and for `MERGE`; adjust `bulk_batch_size()`. |
| **Time zones** | With a time zone table the backend could convert in SQL (`supports_timezones` stays off; the 5 expected failures of `REASON_TIME_ZONE_CONVERSION`). Only if a user needs it. |
| **Performance** | Timings of the own IBM i tests and the supported modules without other load, as a baseline; then the slow spots (catalog queries in introspection, `MERGE` batches, LOB inserts). |

## 6. More IBM i releases and PTF levels
- **Capabilities per TR / PTF Group:** `capabilities.py` has the hook
  (`FeatureProbe`, "none so far"). Read the levels, run the feature probes on each
  level available, and add the capabilities that differ.
- **IBM i 7.6:** a profile `"7.6"`, the probes and the full suite once.
- **IBM i 7.4** (only on request, CLAUDE.md section 3): `BOOLEAN` is missing
  (the `SMALLINT` + `CHECK` fallback behind `has_boolean_type`), JSON needs
  SF99704 levels 4 and 7.

## 7. Other drivers (CLAUDE.md "Later")
Mapepire and `ibm_db` (Python in PASE on the IBM i itself): a second
implementation of `drivers/base.py`, with its own error mapping and type
conversion; needs the dedicated system to run PASE Python. A separate phase if
there is demand.

## Proposed order
1. System setup (section 1), the settings, a first run of the own IBM i tests.
2. Two connections (section 2): `select_for_update` first, as it matters most for
   real use.
3. Test schemas (section 3), then parallel tests.
4. The full suite and its triage (section 4).
5. Sections 5 and 6 as time allows; section 7 only on demand.

## Open questions
1. Which IBM i will it be (own hardware, a cloud partition, a partner system), and
   which releases can it run?
2. May test runs change system-wide settings there (reply list, QAQQINI), or only
   their own job and libraries, as on PUB400?

## Links
- [phase-7.md](phase-7.md), [IBMI_NOTES.md](../IBMI_NOTES.md),
  [Known limitations](../user/Known-Limitations.md), the open tracks in
  `docs/status.toml`.
