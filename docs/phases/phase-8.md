# Phase 8: On a dedicated IBM i

> Status: Approved by the maintainer on 2026-11-11 (the merge of
> [#242](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/242)). It starts when a dedicated IBM
> i is available.

## Goal
Verify and enable what a shared system cannot show: creating schemas and parallel
test runs, the full Django test suite, system-wide settings, more than one Db2 for
i release or PTF level, time zones and performance. Releases 1.x after 1.0.0
([phase 7](phase-7.md)).

Since #234 and #236 PUB400 allows up to three connections for lock and
concurrency tests, so the two-connection work moved to phase 7: the row locks of
`select_for_update()`, `MERGE` under concurrency (done, #238), `LOCK TABLE` (done,
#162, fixed in #241), `test_db_allows_multiple_connections`, the LOB limit for 3
or more LOB columns, and foreign keys across the two journaled libraries.

"Done when" (proposed): every item below is verified on the dedicated IBM i and
either enabled (with an own IBM i test) or documented as a limit with its probe;
the open tracks in `docs/status.toml` that name a dedicated IBM i are closed.

## 1. What the system needs
- IBM i 7.5 (the minimum and primary target), ideally also 7.6, and 7.4 if it is
  ever added (section 5).
- A user profile that may `CREATE SCHEMA` (two schemas of at most 10 characters,
  such as `DJTEST` and `DJTESTOTH`, CLAUDE.md section 6), and the authority to
  change the system reply list or a QAQQINI in its own library, for the CPA32B2
  cases.
- More concurrent connections from the test machine than PUB400's rule allows
  (four at once worked there, at most three are used), for parallel test runs.
- Readable TR and Db2 PTF Group levels (`QSYS2.GROUP_PTF_INFO`), which PUB400 hides.
- No other users' load, so that timings and the full suite are repeatable.

## 2. Creating test schemas and parallel tests
Today tests run in two pre-existing libraries ("use existing schema" mode,
phase 1). With `CREATE SCHEMA` authority: the normal Django mode (create and drop
the test database), journaled automatically, with the existing mode kept for
shared systems. Then **`can_clone_databases`** (a schema per test process) and
`--parallel` greater than 1 for the full suite. Configuration (`TEST`), docs and
own tests for both modes.

**Unskip on a dedicated IBM i:** the Django tests that phase 7 skips because they
need more connections than PUB400's rule allows (`test_db_allows_multiple_connections`,
phase 7 answer 6); the exact list is in [phase-7.md](phase-7.md) once the flag is
on.

## 3. The full Django suite (tier 3)
CLAUDE.md section 6: the source of truth for the flags is Django's whole suite on a
dedicated IBM i, never on PUB400. Approach: `settings_django_suite.py` for the
dedicated schemas, a run of all modules per Django version (with `--parallel`
after section 2), and a triage of every failing module into: backend bug (fix),
Db2 for i limit (reason), not applicable (GIS, PostgreSQL-only). TEST_STATUS then
reports the whole suite next to the supported modules.

## 4. Things a shared system hides
| Item | Approach |
|---|---|
| **CPA32B2 with a system reply list entry** | Verify the behaviour with an `*SYSRPYL` entry instead of the per-job QAQQINI override; the unverifiable goldens mechanism is ready for it (`tests/offline/golden/unverifiable.toml`). A system-wide setting: not on PUB400. |
| **Time zones** | With a time zone table the backend could convert in SQL (`supports_timezones` stays off; the 5 expected failures of `REASON_TIME_ZONE_CONVERSION`). Only if a user needs it. |
| **Performance** | Timings of the own IBM i tests and the supported modules without other load, as a baseline; then the slow spots (catalog queries in introspection, `MERGE` batches, LOB inserts). |
| **Free-threaded Python** (`3.15t`, #233) | Needs several connections and threads at once to show anything; after checking whether Django supports it. |

## 5. More IBM i releases and PTF levels
- **Capabilities per TR / PTF Group:** `capabilities.py` has the hook
  (`FeatureProbe`, "none so far"). Read the levels, run the feature probes on each
  level available, and add the capabilities that differ.
- **IBM i 7.6:** a profile `"7.6"`, the probes and the full suite once.
- **IBM i 7.4** (only on request, CLAUDE.md section 3): `BOOLEAN` is missing
  (the `SMALLINT` + `CHECK` fallback behind `has_boolean_type`), JSON needs
  SF99704 levels 4 and 7.

## 6. Other drivers (CLAUDE.md "Later")
Mapepire and `ibm_db` (Python in PASE on the IBM i itself): a second
implementation of `drivers/base.py`, with its own error mapping and type
conversion; needs the dedicated system to run PASE Python. A separate phase if
there is demand.

## Proposed order
1. System setup (section 1), the settings, a first run of the own IBM i tests.
2. Test schemas, then parallel tests (section 2).
3. The full suite and its triage (section 3).
4. Sections 4 and 5 as time allows; section 6 only on demand.

## Open questions
1. Which IBM i will it be (own hardware, a cloud partition, a partner system), and
   which releases can it run?
2. May test runs change system-wide settings there (reply list, QAQQINI), or only
   their own job and libraries, as on PUB400?

## Links
- [phase-7.md](phase-7.md), [IBMI_NOTES.md](../IBMI_NOTES.md),
  [Known limitations](../user/Known-Limitations.md), the open tracks in
  `docs/status.toml`.
