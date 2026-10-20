# Offline query corpus

> Status: Approved, 2026-10-19

The maintainer's answers to the open questions are in "Decisions" at the end.

## Goal
Get as many offline tests as possible out of the Django tests we already run
on PUB400. Every SQL statement that a passing Django test sent to Db2 for i
becomes an offline regression check, without writing the cases by hand.

Two parts:
- **A, DDL corpus:** the schema SQL (`CREATE TABLE`, indexes, constraints) for
  every model of the Django test apps we run.
- **B, query corpus:** for each Django test, the pickled `Query` objects
  together with the SQL and params our backend produced for them on PUB400.

B comes first. A follows in a small second PR once the capture hook exists
(decision 1).

The capture on PUB400 is **not** part of this proposal. It is a follow-up that
the main session runs (see "Follow-up").

**Why now:** the 6.1 corpus must exist before the phase 3 compat changes (see the phase 3 plan,
[phase-3.md](../phases/phase-3.md) from
[#86](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/86),
decision 6). The compat changes touch
`expressions.py`, `operations.py` and the test lists. A corpus captured
before them guards that the SQL our backend writes for Django 6.1 stays
unchanged while 6.0 and 5.2 support is added.

## Feasibility check (offline only, done)
I ran a throwaway script outside the repository (in the worktree's
gitignored `test-results/`) to check whether the idea works.

Setup:
- Django `stable/6.1.x` (`6762bd7`); the backend at `main` `18eded3`; Python
  3.14; the `offline` image.
- `pyodbc.connect` was replaced with a function that raises.
- `DatabaseWrapper.get_new_connection` returned an in-memory fake connection
  that returns no rows (and `IDENTITY_VAL_LOCAL()` values for inserts).
- The `7.5` capability profile, as in `tests/django_settings/settings_offline.py`.
- No IBM i connection.

**B, query corpus, on Django's `ordering` tests (43 tests: 35 `TestCase`, 8
`SimpleTestCase`):**
1. **Capture:** the script ran the module with unittest against the fake
   connection. A wrapper around `SQLCompiler.execute_sql` and
   `SQLInsertCompiler.execute_sql` recorded, before each execution: the test
   id, the compiler class, `as_sql()` (SQL plus `repr` of each param) and
   `pickle.dumps(compiler.query)`.
   - The fake connection returns no rows, so assertions were made lenient:
     querysets passed to them are still evaluated, then the assertion is
     skipped. Otherwise each test would stop at its first query.
2. **Replay:** a fresh Python process unpickled each `Query`, compiled it again
   with `query.get_compiler(connection=connection).as_sql()`, and compared
   SQL and params.

Results:

| Measure | Result |
|---|---|
| Statements recorded | 129: 68 SELECT, 45 INSERT (8 of them from `setUpTestData`), 16 UPDATE |
| Tests with records | 33 of the 35 `TestCase` tests, plus `setUpTestData` |
| Not picklable | 0 |
| No SQL at capture | 1: a `FieldError`, in a test that expects that error |
| Unpickle errors | 0 |
| Recompile errors | 0 |
| **Replayed SQL and params identical** | **128 of 128** |
| Unique SQL (whitespace-normalized) | 108 |
| Size | about 1.4 KB per pickled Query (base64; maximum 3.3 KB) plus about 0.26 KB of SQL |
| Replay time | under 0.1 s for 129 entries, on top of about 1.7 s for Django setup |

To check that a corpus catches backend changes, the replay was run once more
with a deliberate change: `limit_offset_sql` writing `LIMIT`/`OFFSET`. It
reported **7 mismatches**, exactly the sliced querysets, and 121 matches.

**A, DDL corpus, on the `ordering` models:**
- `connection.schema_editor(collect_sql=True)` produced 17 statements for the
  10 models (CREATE TABLE, CREATE INDEX, a UNIQUE constraint) with no
  connection.
- One catch: calling `create_model()` on every model also produced `CREATE
  TABLE "ORDERING_ARTICLE" ();` twice, for the proxy models. The generator has
  to pick models the way Django's test database setup does (managed,
  non-proxy, migrations where an app has them). Recording what the PUB400 run
  actually executed avoids that guesswork, which is the proposal below.

**Not checked by this feasibility run:**
- other modules;
- replay on Python 3.12 and 3.13 (both sides ran on 3.14);
- pickles across Django versions;
- the capture inside `runtests.py` itself.

## What it catches, and what it does not
- **Catches:** any backend change that alters the SQL or params of a statement
  that a previously passing Django test sent to Db2 for i. This covers
  compiler, expression, operations and capability changes, in every Python ×
  Django CI job, with no IBM i.
- **Does not catch:**
  - Whether new or changed SQL is correct: that still needs one PUB400 run of
    the affected tests.
  - Behaviour that is not SQL text, such as converters, driver parameter
    handling, the identity-restart sequence, connection state and error
    mapping.
  - Tests that never ran on PUB400.
- **A mismatch is not automatically a bug.** It means "this SQL is no longer
  the SQL that passed on IBM i", the same rule as for the hand-written goldens.

## Design

### One corpus per Django version
Pickles are not portable between Django versions, and they refer to the test
apps' models by import path (`ordering.models.Article`). So there is one
corpus per Django version (5.2, 6.0, 6.1):
- each corpus records the Django commit it was captured with;
- the corpus step installs **Django itself from exactly that commit**: both
  the library and the test suite (`tests/` on `sys.path`). It never uses the
  latest PyPI patch release; otherwise a Django patch release could break the
  corpus without any backend change;
- a corpus is replayed only by the jobs of its own Django series
  (`compat.DJANGO_SERIES`).

**When the `vendor/` checkout is bumped** (a new commit on `stable/<x.y>.x`):
1. Replay the corpus offline against the new commit first.
2. If every entry matches, the manifest's commit moves to the new commit in
   the same PR as the bump.
3. If entries differ, the change comes from Django, not the backend. The
   corpus keeps the old commit, so CI stays green on it, and the next PUB400
   run of the affected modules on the new checkout re-captures them. The
   re-capture moves the manifest to the new commit; the PR shows the SQL
   differences.

### Layout and format

```
tests/offline/corpus/<django>/<profile>/
    manifest.toml             # Django commit, capture level, capture date, counts
    queries/<module>.jsonl.gz # B: one JSON object per unique statement (gzip)
    queries/<module>.sql      # B: plain index of the unique SQL, for review
    ddl/<module>.sql          # A (second PR): DDL in execution order, golden-style header
```

Each query entry holds:
- `tests`: the test ids that ran it;
- `compiler`;
- `sql`: list of `[sql, params]` (params tagged as in the golden files);
- `query`: base64 pickle, protocol 5;
- `verified`: the stamp (see below).

The SQL comes first and is readable, so a corpus diff in a PR shows the SQL
change.

### Dedup
- The key is the compiler class plus whitespace-normalized SQL plus the
  tagged params. The first pickle is kept, and the test ids are merged.
- In the check above, dedup removed 16% (108 unique of 129). Most duplicates
  are `setUpTestData` inserts and repeated lookups.

### Unpicklable queries
Skip and count them, never fail the capture:
- at capture: `pickle.dumps` errors;
- at replay: unpickle errors (for example a model defined inside a test with
  `isolate_apps`, which cannot be imported again).

Each module's manifest records recorded / unique / unpicklable /
not-replayable counts. The offline report prints the coverage per module:
entries replayed, out of statements recorded.

### Expected size
**First capture (2026-10-20, `ordering` on Django 6.1 at `1e01021`, PUB400):**
43 tests passed; 138 statements kept, 115 unique, 0 unpicklable, 1 not
compiled (a test that expects a FieldError); 208 KB of JSONL, **18 KB gzip
(about 9 %)**, plus a 26 KB SQL index; all 115 replay identically on Python
3.12, 3.13 and 3.14. At that ratio about 4,000 entries per version come to
about 0.6 MB per version, not 7 MB.

The extrapolation before the first capture:
- The modules in [TEST_STATUS.md](../TEST_STATUS.md) have about 1,250 tests.
  At `ordering`'s rate (about 3.7 statements per test, 84% unique), that is
  about 4,000 unique entries per Django version.
- At about 1.7 KB each, that is about 7 MB per version uncompressed, so about
  20 MB for three versions.
- That is too large to keep as plain text. Decided (decision 4):
  - gzip each `queries/<module>.jsonl.gz` (the ratio is not measured yet);
  - keep a plain-text `queries/<module>.sql` index with the unique SQL only,
    for review;
  - no Git LFS (bandwidth quota on public repositories, CI cost).
- `setUpTestData` inserts are kept, because they test the insert path; dedup
  removes repeats (decision 3).
- **Stable files:** a refresh keeps unchanged entries byte-identical and
  rewrites only the modules whose SQL changed, so git history does not grow on
  every run. In practice:
  - entries in a fixed order (by key);
  - deterministic JSON (sorted keys, fixed separators);
  - gzip with a fixed header (`mtime=0`, no file name);
  - an unchanged module file is not rewritten at all.

### Capture hook (for the follow-up)
- A small module under `tests/` is enabled only by an environment variable
  in `scripts/run_django_tests.py`, never in the backend package.
- It wraps `SQLCompiler.execute_sql` (and the insert compiler's) as in the
  check above. It records before executing, and catches every exception of
  its own, so it can never change a test's outcome.
  - *Implemented (2026-10-20):* the recorded SQL comes from a fresh compiler on
    the **unpickled** copy of the query, exactly as the replay compiles it,
    never from `as_sql()` on the live compiler (which can have side effects,
    e.g. an update's related-update filter). Each entry also records the
    `USE_TZ` / `TIME_ZONE` the test ran with; the replay applies them again.
- A custom test result keeps an entry only if the test **passed**. Entries
  from failures, errors, skips and expected failures are dropped (decision 2).
- For A (second PR), the hook also records the DDL that the test database setup executes
  (`schema_editor.execute`). Offline, the same DDL is generated with
  `collect_sql=True` for the same models and compared.

### Verification stamps
Stamps follow the existing goldens; see
[DECISIONS.md](../DECISIONS.md#2026-10-17-golden-file-format-and-verification),
#58, `tests/golden.py`, `tests/pub400/test_goldens.py` and
`tests/offline/golden/last-verification.txt`:
- An entry carries the same stamp format:
  `IBM i 7.5 on PUB400 (TR <n>, Db2 PTF Group <n>), Django <version>, <date>`.
  The level is taken from the capture run.
- Meaning: stronger than a golden's "accepted by Db2 for i". The statement was
  executed by a Django test that **passed**, so its results satisfied
  Django's assertions.
- **DDL** entries count as verified when the PUB400 run executed exactly that
  DDL while creating the test tables.
- An entry is re-stamped only when it is new or was verified on another
  level, as for goldens. A capture on the same level leaves stamps and dates
  alone.
- An offline mismatch fails the test. `--update-corpus` (refused when `CI` is
  set) writes the new SQL and **clears** the stamp, like `--update-goldens`.
- Unverified entries are listed in the report. A later capture of that module
  verifies them, or they are dropped.
- The latest capture per version goes to one report file,
  `tests/offline/corpus/<django>/last-capture.txt`.

### nox and CI
- A nox session, `corpus`, is parametrized exactly like `offline` (every
  Python × Django version).
  - It runs in its own process with settings that install the corpus
    modules' apps; the offline settings stay as they are.
  - It installs Django from the corpus's commit (see above), not from PyPI.
- The connection guard stays: `pyodbc.connect` raises, and the fake
  connection never reaches a driver.
- CI (`.github/workflows/offline.yml`, from #87): the corpus is **a separate
  step inside each offline job**, not a separate job (decision 5). The
  required `offline` check therefore covers it.
- Each job fetches that one Django commit shallowly, about 10–30 s
  (estimated).
- Expected extra time per job: setup about 2 s, plus a few seconds to replay
  about 4,000 entries (the check above replayed 129 in under 0.1 s), plus the
  fetch. Under 1 minute in total (estimated).

### Refreshing and review
Refresh happens only from PUB400 runs, by the main session, never in CI. Both
kinds of run refresh (decision 6):
- **Module runs during development:** a backend PR that changes SQL reruns
  the affected Django modules on PUB400, as it already does. With the capture
  enabled, the same run refreshes those modules' corpus files in the same PR.
  The PR shows the SQL diff together with its verification.
- **Release runs:** refresh every module for every supported version.
- **Review:** the PR diff of `queries/<module>.sql` shows added, removed and
  changed SQL; the pickles are opaque and are not reviewed line by line. A
  summary (counts per module, unverified entries) is generated for the PR
  description.
- **Pickle safety:** unpickling runs code. The corpus is only read from files
  in this repository, which reach `main` through reviewed, signed PRs. It is
  never fetched from elsewhere.

## Follow-up (main session, PUB400)
Order: tag 0.1.0a3, then #69, then this corpus for 6.1, then phase 3 step A.

1. Capture hook, offline replay (the `corpus` session, as a step in each
   offline CI job) and the report, as a PR with only offline tests.
2. First capture: `ordering` on 6.1, to compare the real numbers with this
   check.
3. Capture the other modules in TEST_STATUS.md, one module per run,
   sequentially and with one connection, as usual on PUB400.
4. A, the DDL corpus, in a small second PR once the capture hook exists.
5. 6.0 and 5.2 corpora with phase 3 (release run).

## Decisions
Approved by the maintainer on 2026-10-19
([DECISIONS](../DECISIONS.md#2026-10-19-offline-query-corpus-captured-on-pub400-replayed-offline)):

1. **Scope:** B (the query corpus) first. A (the DDL corpus) follows in a
   small second PR once the capture hook exists.
2. **Only passing tests count.** Expected failures are excluded.
3. **`setUpTestData` inserts are kept**, because they test the insert path.
   Dedup removes repeats.
4. **Storage:** gzip JSONL per module plus a plain SQL index. No Git LFS
   (bandwidth quota on public repositories, CI cost). A refresh keeps
   unchanged entries byte-identical and rewrites only modules whose SQL
   changed, so git history does not grow on every run.
5. **CI:** a separate step inside each offline job, not a separate job.
6. **Refresh:** both module runs in backend PRs and release runs.

Requirements the maintainer added:
- The corpus step installs Django from exactly the commit the corpus was
  captured with, both the library and the test suite, not the latest PyPI
  patch release.
- When `vendor/` is bumped, replay offline first; if entries differ,
  re-capture in the next PUB400 run.
- The 6.1 corpus must exist before the phase 3 compat changes, so it guards
  that the 6.1 SQL stays unchanged.
