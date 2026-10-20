# Phase 3: Django 6.0 and 5.2 support

> Status: Done (2026-10-21)

## Goal
From CLAUDE.md section 9: work backwards in two steps, 6.1 → 6.0 first, then
6.0 → 5.2; build `compat.py` from real differences, extend the nox matrix, fill
`DJANGO_VERSIONS.md`. Python 3.12, 3.13 and 3.14 on every supported Django
version; no `django.VERSION` check outside `compat.py`.

"Done when", per step (from the approved plan, 2026-10-19): the backend
imports and passes the offline tier on every Python × that Django version with
goldens for that series, the pub400 tier passes on that version, and
`DJANGO_VERSIONS.md` records the backend API impact. At the end, the release
run passes on 5.2, 6.0 and 6.1. All of it was met.

The approved plan, with its analysis of the three Django versions
(`stable/6.1.x` `1e01021`, `stable/6.0.x` `52e5ba1`, `stable/5.2.x` `cae7247`),
is in this file's history (#86); the per-version impact is kept up to date in
[DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md).

## What was done

**Before step A** (the approved order: 0.1.0a3, then #69, then the 6.1 corpus)
- Numeric filter values that do not fit the column get their own `DECIMAL`
  type (issue #69). [#97](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/97)
- Offline query corpus for Django 6.1: capture hook and replay, the capture
  never executes SQL, pickle format 2 for model classes, volatile records
  dropped, then all seven supported modules (2533 entries).
  [#100](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/100), [#101](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/101), [#102](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/102), [#103](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/103), [#104](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/104), [#105](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/105), [#109](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/109)
- CHECK constraint violations (SQL0545, reported as `HY000`) raise
  `IntegrityError` (issue #96, part). [#99](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/99), [#106](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/106)

**Step A: Django 6.1 → 6.0**
- `compat.py` in three sections (6.0 only / 5.2 only / before 6.1) and an
  offline guard against Django version checks elsewhere. [#107](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/107)
- The duration range check before 6.1: `compat.install_duration_adapter()`
  routes `DurationField` values through `adapt_durationfield_value()` for this
  backend's connections only; every path tested offline and on PUB400. Django
  6.0 in the matrix, pyproject `Django>=6.0.3`, 154 goldens for 6.0 (they
  differ from 6.1's only in unquoted subquery aliases), all verified. [#110](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/110)
- The release run as one nox session; the Mac kept awake during PUB400 runs;
  the backend commit recorded for runs from a git worktree; the tier log kept
  out of the module logs. [#111](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/111), [#108](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/108), [#112](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/112), [#116](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/116)
- Release runs on 6.0 and 6.1 and the status from them. [#114](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/114)

**Step B: Django 6.0 → 5.2**
- The 5.2 section of `compat.py`: `StringAgg` not supported on 5.2 (the
  backend would not load), the tuple-subquery comparison refused as on 6.0+.
  [#113](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/113)
- `DROP COLUMN` probed with and without `CASCADE` (QTEMP); the same SQL pinned
  for every version. [#115](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/115)
- Django 5.2 in the matrix, pyproject `Django>=5.2.12,!=6.0.0,!=6.0.1,!=6.0.2,<6.2`,
  153 goldens (6.0's without the two `StringAgg` cases), 152 verified.
  [#117](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/117)
- The release run on 5.2 and the status from it. [#118](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/118)

**Tooling and documentation**
- README redesign: one badge per IBM i / Python / Django version with its
  state, a test status per Django version over four named test sets,
  `docs/FEATURES.md` and `docs/OFFLINE_CORPUS.md`. [#120](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/120)
- The wheel session (run by the release workflow) works again. [#119](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/119)
- This record, the user docs on supported versions, 5.2 marked supported.

## Key decisions
The plan's decisions (approved 2026-10-19) and those made during the phase:
- `compat.py` in three sections: [DECISIONS](../DECISIONS.md#2026-10-19-compatpy-in-three-sections-60-only-52-only-before-61)
- Minimum patch releases 5.2.12, 6.0.3 and 6.1.0: [DECISIONS](../DECISIONS.md#2026-10-19-minimum-django-patch-releases-5212-603-and-610)
- `StringAgg` requires Django 6.0+: [DECISIONS](../DECISIONS.md#2026-10-19-stringagg-requires-django-60-imported-through-compatpy)
- The duration range check on every version, then how before 6.1 (a scoped
  wrapper, not a hook): [DECISIONS](../DECISIONS.md#2026-10-19-the-duration-range-check-on-every-supported-django-version), [DECISIONS](../DECISIONS.md#2026-10-20-the-duration-range-check-before-django-61)
- `DROP COLUMN` SQL pinned for every version after a QTEMP probe: [DECISIONS](../DECISIONS.md#2026-10-19-drop-column-sql-pinned-for-every-version-after-a-qtemp-probe)
- The release run as one nox session: [DECISIONS](../DECISIONS.md#2026-10-19-the-release-run-as-one-nox-session)
- The offline query corpus and its capture rules: [DECISIONS](../DECISIONS.md#2026-10-19-offline-query-corpus-captured-on-pub400-replayed-offline), [DECISIONS](../DECISIONS.md#2026-10-20-offline-query-corpus-capture-from-an-unpickled-copy-settings-per-entry), [DECISIONS](../DECISIONS.md#2026-10-20-the-corpus-capture-hook-never-executes-sql), [DECISIONS](../DECISIONS.md#2026-10-20-corpus-pickles-store-model-classes-by-app-label-and-model-name), [DECISIONS](../DECISIONS.md#2026-10-20-the-corpus-capture-drops-records-that-compile-differently-at-the-end-of-the-run)
- Numeric filter values out of range: [DECISIONS](../DECISIONS.md#2026-10-20-numeric-filter-values-that-do-not-fit-the-column-get-their-own-decimal-type)
- All goldens of 6.0 and 5.2 verified on PUB400, not only those that differ
  (decision 8 of the plan).

## IBM i findings
- Constraint violations: duplicate key and NOT NULL arrive as `23000`, CHECK
  (SQL0545) as `HY000`; QTEMP takes no constraints: [IBMI_NOTES](../IBMI_NOTES.md#constraint-violations-sqlstate-and-sqlcode-nox--s-probe----constraint_errors)
- `DROP COLUMN` with no keyword, `RESTRICT` or `CASCADE`: all valid, all
  cancelled by CPA32B2 before any dependency handling; the default is not
  determinable on PUB400: [IBMI_NOTES](../IBMI_NOTES.md#drop-column-with-and-without-cascade-nox--s-probe----drop_column)
- Numeric values that do not fit the column: [IBMI_NOTES](../IBMI_NOTES.md#numeric-values-that-do-not-fit-the-column-nox--s-probe----numeric_params)
- Every golden of 6.0 (154) and 5.2 (152 of 153) accepted by Db2 for i; the
  one left is the `DROP COLUMN` golden, cancelled on PUB400.

## Test status at the end of the phase
Release runs on PUB400 (IBM i 7.5), Python 3.14, one connection at a time:
6.0 and 6.1 at `218bfca`, 5.2 at `1117fb5` (the same backend code plus #115's
`DROP COLUMN` pin), 17 runs each, all passed ([TEST_STATUS](../TEST_STATUS.md)):

| Test set | Django 6.1 | Django 6.0 | Django 5.2 |
|---|---|---|---|
| Offline · own tests | 2232 passed, 2 skipped | 2234 passed | 2232 passed |
| IBM i · own tests | 245 passed, 1 expected failure | 245 passed, 1 expected failure | 240 passed, 3 skipped, 2 expected failures |
| IBM i · Django test suite | 1249 tests: 1189 passed, 53 skipped, 7 expected failures | 1159 tests: 1110 passed, 41 skipped, 8 expected failures | 1144 tests: 1098 passed, 38 skipped, 8 expected failures |
| Offline · Django test suite (replay) | 2533 entries identical | no corpus yet | no corpus yet |

- No version needed its own skip or expected failure; the test counts differ
  because each version's test suite differs. The three skips of the IBM i ·
  own tests on 5.2 are `StringAgg` and `AnyValue` (Django 6.0+).
- Goldens: 463, 3 unverified (the `DROP COLUMN` golden of each series).
- 0 failed anywhere.

## Carried forward
- 6.0 and 5.2 query corpora (capture with the next release run).
- Db2 for i's `DROP COLUMN` default (CASCADE or RESTRICT): needs a system
  reply list entry for CPA32B2, so a system other than PUB400 and the
  maintainer's approval.
- Foreign key violations (SQL0530 / 0531 / 0532) → `IntegrityError` when the
  schema editor creates foreign keys (phase 4/5), issue [#96](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/96).
- From the plan: compat names for `returning_columns` / `fetch_returned_rows`
  (phase 5); `get_relations` 3-tuples and `supports_inspectdb` (phase 4);
  `binary_placeholder_sql` (binary values); DB-level `on_delete`, 6.1+ (phase 6).
- The code rename to the four test set names (one mechanical PR when no other
  PRs are open); whether CI runs the wheel session too (#119).
- Open issues: [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82) (`annotations` / `expressions_case`), [#23](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/23) (column order, phase 4), [#94](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/94) (release workflow variable).
- When Django 6.2 LTS ships, the same steps apply forwards; 6.0 is dropped in
  the first release after April 2027.

## Links
- [DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md), [FEATURES.md](../FEATURES.md),
  [OFFLINE_CORPUS.md](../OFFLINE_CORPUS.md), [TEST_STATUS.md](../TEST_STATUS.md).
- Changelog: the fragments in `changelog.d/` until the next release.
- The approved plan: this file at the merge of #86.
