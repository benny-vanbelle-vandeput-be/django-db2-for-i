# Offline query corpus

The test set **"Offline · Django test suite (replay)"**: every statement that
a passing test of Django's own test suite sent to Db2 for i is recorded once on
IBM i, and GitHub CI compiles it again on every commit, without an IBM i, and
compares. A difference means "this is no longer the SQL that passed on IBM i".

This page is the reference. The design was approved on 2026-10-19
([proposal](proposals/offline-query-corpus.md),
[DECISIONS](DECISIONS.md#2026-10-19-offline-query-corpus-captured-on-pub400-replayed-offline)).

## How it works

1. **Capture, on IBM i.** `scripts/runtests.sh <django> --clean --capture <label>`
   runs a Django test module with a capture hook (`tests/corpus/capture.py`).
   Before Django executes a statement, the hook pickles the compiler's query,
   loads a **fresh copy** and compiles it, exactly as the replay will. It
   records the test id, the compiler class, the SQL with typed params, the
   pickle and the `USE_TZ` / `TIME_ZONE` in effect. Only tests that **passed**
   count; statements of `setUpTestData` count if a test of that class passed.
   Each record is compiled once more at the end of the run, and records whose
   SQL changed in the meantime are dropped (see "Volatile" below).
2. **Build.** `scripts/build_corpus.py <django>` turns the raw captures in
   `test-results/<django>/corpus/` into
   `tests/offline/corpus/<django>/<profile>/`: per Django test module one gzip
   JSONL file (deduplicated by compiler, normalized SQL, params and settings)
   and one plain-text SQL index for review, plus `manifest.toml` with the
   Django commit and the counts per module. Unchanged modules stay
   byte-identical (gzip with mtime 0).
3. **Replay, offline.** `nox -s "corpus(<python>-django<django>)"` installs
   Django, library and test suite, from **exactly the manifest's commit**
   (vendor checkout or a shallow fetch), loads every pickle, compiles it under
   the offline capability profile with the entry's settings, and compares SQL
   and params. CI runs it as a step of each offline job.

## Numbers

**Django 6.1** (commit `1e01021`, profile 7.5, captured 2026-10-20 on PUB400):

| Module | Recorded | Unique | Unpicklable | Needs database | No SQL | Not compiled | Volatile | Pickle format | gzip |
|---|---|---|---|---|---|---|---|---|---|
| aggregation | 367 | 347 | 5 | 0 | 6 | 6 | 0 | 2 | 129 KB |
| basic | 237 | 187 | 0 | 0 | 0 | 4 | 0 | 1 | 22 KB |
| expressions | 590 | 423 | 3 | 1 | 0 | 6 | 0 | 1 | 102 KB |
| lookup | 354 | 296 | 1 | 0 | 10 | 5 | 0 | 2 | 70 KB |
| ordering | 138 | 115 | 0 | 0 | 0 | 1 | 0 | 1 | 18 KB |
| queries | 1455 | 1145 | 1 | 3 | 49 | 11 | 4 | 2 | 414 KB |
| transactions | 209 | 20 | 0 | 0 | 0 | 1 | 0 | 1 | 4 KB |
| **Total** | **3350** | **2533** | **10** | **4** | **65** | **34** | **4** | | **759 KB** |

All 2533 entries replay identically on Python 3.12, 3.13 and 3.14 (0 not
loadable, 0 not replayable, 0 different). **Django 6.0 and 5.2** have no corpus
yet: the phase 3 release runs on them did not capture (`release_run` lacked
`--capture`); every release run captures now, starting with the end of phase 3.

## What the counts mean

- **Recorded / unique:** statements kept from passing tests, and the entries
  left after deduplication.
- **Unpicklable:** the query could not be pickled, nearly always a class
  defined inside a test (a custom aggregate or expression), which cannot be
  loaded again anyway.
- **Needs database:** compiling the copy would execute SQL (an update over a
  join that pre-selects its primary keys, or an update with related
  updates). The hook blocks every execution during its own compile; such
  statements are counted, not recorded.
- **No SQL:** the query matches nothing (`EmptyResultSet`); Django sends no SQL.
- **Not compiled:** the copy raised another error (for example a test that
  expects a `FieldError`).
- **Volatile:** the record compiled differently at the end of the run: an
  insert with an `auto_now` field (the clock), or a model option a test changes
  and restores. It could never replay identically, so it is dropped.
- **Not loadable / not replayable** (replay): the pickle cannot be loaded, or
  compiling it would need the database. Both are reported as skipped.

## Pickle formats

The manifest records each module's `pickle_format`; the replay loads both.

- **1:** a plain pickle (the first captures: ordering, basic, transactions,
  expressions).
- **2:** a private Pickler stores model classes as persistent ids
  `("model", app_label, model_name)`, resolved through the app registry on
  load; everything else stays a plain pickle. Plain pickle stores a class by
  its module path, and an auto-created many-to-many through model is not a
  module attribute, so before format 2 every query on one failed (74 of
  aggregation's 79 unpicklable statements)
  ([DECISIONS](DECISIONS.md#2026-10-20-corpus-pickles-store-model-classes-by-app-label-and-model-name)).

## Lessons from building it

- **The hook never executes SQL.** The first capture compiled the copy
  normally, and an update with related updates ran an extra `SELECT` inside the
  test. The tests still passed, but `assertNumQueries` could have failed, and
  the hook must never change what a test does. Every execution is now blocked
  during the hook's own compile. An offline test runs the same workload on
  SQLite with and without the hook and requires identical statements
  ([DECISIONS](DECISIONS.md#2026-10-20-the-corpus-capture-hook-never-executes-sql)).
- **Record from a fresh copy, not from the live compiler.** `as_sql()` on the
  live compiler can have side effects, and the replay compiles a copy too
  ([DECISIONS](DECISIONS.md#2026-10-20-offline-query-corpus-capture-from-an-unpickled-copy-settings-per-entry)).
- **State at capture time.** Two kinds of record can never replay
  identically: the clock in `auto_now` fields, and model options a test
  changes and restores. The end-of-run check drops them
  ([DECISIONS](DECISIONS.md#2026-10-20-the-corpus-capture-drops-records-that-compile-differently-at-the-end-of-the-run)).
- **Keep the Mac awake.** A capture that slept lost its TLS connection
  (`08S01`); PUB400 runs go through `scripts/pub400.sh`, which uses
  `caffeinate` on macOS.

## Refreshing a corpus

1. On IBM i, capture each label of the module, one PUB400 run at a time:
   `scripts/runtests.sh <django> --clean --capture <label>`. Build a module
   only from captures of **all** its labels (for `queries`, all ten).
2. Build: `docker compose run --rm tests sh -c 'uv run --no-project --python 3.14
   python scripts/build_corpus.py <django> test-results/<django>/corpus/<module>*.jsonl'`.
   The build refuses captures from different Django commits or pickle formats.
3. Replay on every Python: `nox -s corpus`. It must pass before the corpus is
   committed.
4. Commit one module per commit, with the counts (recorded, unique,
   unpicklable, needs database, no SQL, not compiled, volatile, not
   replayable, size) in the pull request.

A bumped `vendor/` Django checkout is replayed offline first; modules whose
entries differ are captured again on the next PUB400 run.

## Reviewing corpus changes

- Review the plain-text index `queries/<module>.sql` (one unique statement per
  line), not the gzip file: its diff shows exactly which SQL appeared,
  disappeared or changed.
- Check the manifest diff: the counts per module, the Django commit, the
  verification level.
- An intended SQL change in the backend shows up as replay mismatches.
  `pytest ... --update-corpus` (never in CI) rewrites those entries and clears
  their verification stamp, like `--update-goldens`; the new SQL is verified on
  the next capture.
