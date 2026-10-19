# Offline query corpus

> Status: Proposed, not yet approved

## Goal
Get as many offline tests as possible out of the Django tests we already run
on PUB400. Every SQL statement that a passing Django test sent to Db2 for i
becomes an offline regression check, without writing the cases by hand.

Two parts:
- **A, DDL corpus:** the schema SQL (`CREATE TABLE`, indexes, constraints) for
  every model of the Django test apps we run.
- **B, query corpus:** for each Django test, the pickled `Query` objects
  together with the SQL and params our backend produced for them on PUB400.

The capture on PUB400 is **not** part of this proposal. It is a follow-up that
the main session runs once this proposal is approved (see "Follow-up").

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
- replay needs that version's test-suite checkout, at that commit, on
  `sys.path`;
- a corpus is replayed only by the jobs of its own Django series
  (`compat.DJANGO_SERIES`).

### Layout and format

```
tests/offline/corpus/<django>/<profile>/
    manifest.toml          # Django commit, capture level, capture date, counts
    ddl/<module>.sql       # A: DDL statements in execution order, golden-style header
    queries/<module>.jsonl # B: one JSON object per unique statement
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
This is an extrapolation from one module, to be replaced by real numbers
after the first capture:
- The modules in [TEST_STATUS.md](../TEST_STATUS.md) have about 1,250 tests.
  At `ordering`'s rate (about 3.7 statements per test, 84% unique), that is
  about 4,000 unique entries per Django version.
- At about 1.7 KB each, that is about 7 MB per version uncompressed, so about
  20 MB for three versions.
- That is too large to keep as plain text. Proposed:
  - gzip each `queries/<module>.jsonl.gz` (pickles compress well; the ratio
    is not measured yet);
  - keep a plain-text `queries/<module>.sql` index with the unique SQL only,
    for review;
  - leave insert statements from `setUpTestData` out unless they are unique
    (the maintainer decides, open question 3).

### Capture hook (for the follow-up)
- A small module under `tests/` is enabled only by an environment variable
  in `scripts/run_django_tests.py`, never in the backend package.
- It wraps `SQLCompiler.execute_sql` (and the insert compiler's) as in the
  check above. It records before executing, and catches every exception of
  its own, so it can never change a test's outcome.
- A custom test result keeps an entry only if the test **passed**. Entries
  from failures, errors, skips and expected failures are dropped.
- For A, the hook also records the DDL that the test database setup executes
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
  Python × Django version). It runs in its own process with settings that
  install the corpus modules' apps (the offline settings stay as they are).
- The connection guard stays: `pyodbc.connect` raises, and the fake
  connection never reaches a driver.
- CI ([#87](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/87)):
  the matrix comes from the noxfile, so the `corpus` sessions become parallel
  jobs next to `offline`, or a second step in the same job (open question 5).
  Either way the required `offline` check aggregates them.
- Each job needs the Django test suite at the corpus's commit: a shallow fetch
  of that one commit, about 10–30 s (estimated).
- Expected duration per job: setup about 2 s, replay of about 4,000 entries a
  few seconds (the check above replayed 129 in under 0.1 s), plus the fetch.
  Under 1 minute per job (estimated).

### Refreshing and review
Refresh happens only from PUB400 runs, by the main session (never in CI):
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

## Follow-up (after approval; main session, PUB400)
1. Capture hook, offline replay (`tests/offline/test_corpus.py` or the
   `corpus` session) and the report, as a PR with only offline tests.
2. First capture: `ordering` on 6.1, to compare the real numbers with this
   check.
3. Capture the other modules in TEST_STATUS.md, one module per run, sequential
   and with one connection, as usual on PUB400.
4. 6.0 and 5.2 corpora with phase 3 (release run).

## Open questions for the maintainer
1. **Scope:** start with B only (the larger gain), or A and B together?
2. **Which tests count:** only passing tests (as proposed), or also expected
   failures, whose SQL ran but whose result is known to be wrong?
3. **Inserts from `setUpTestData`:** keep them (they test the insert path) or
   leave them out to save space?
4. **Storage:** gzip JSONL plus a plain SQL index (as proposed), or plain JSONL
   with a size limit, or Git LFS?
5. **CI:** a separate `corpus` job per combination, or a step inside each
   `offline` job?
6. **Refresh:** release runs only, or also module runs in backend PRs (as
   proposed)?
