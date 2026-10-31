# Phase 6: Advanced

> Status: Proposed, not yet approved. No implementation until it is approved.

## Goal
From CLAUDE.md section 9: **advanced**: window functions, `JSONField`, db
functions, DB-level `on_delete` (6.1+), plus the flags moved to phase 6 earlier
(#191, topic 3; the phase 2 query flags; the row locks of `select_for_update()`).

"Done when" (proposed):
- **The Django modules `db_functions` and `expressions_window` and the label
  `model_fields.test_jsonfield` run on 6.1, 6.0 and 5.2 against PUB400 without
  failures or errors**: every remaining failure is a skip or expected failure with
  one fixed reason, and they join the supported modules (`docs/status.toml`, the
  status run). The DB-level `on_delete` tests in `delete` and `schema` do the same
  on 6.1.
- **No flag is `planned = "phase 6"`** in [features.toml](../features.toml): each is
  on where the tests back it, or intentionally off with a one-line reason; each
  flag that goes on comes with an own IBM i test of the real-world pattern
  (CLAUDE.md section 2).
- **Goldens** for every new SQL shape, per Django series, all verified on PUB400.
- **The probe results** decisions rest on are in IBMI_NOTES and `probes/results/`.
- **Known Limitations** states what users must know, in plain words, in the same PR
  as each change.

## 1. Where the backend stands
- **Functions:** expressions are overridden with `as_db2_for_i` methods
  (`expressions.py`, Django's extension point for third-party backends). `Extract`,
  `Trunc`, `Avg`, `StringAgg` and durations exist. Every other function goes out with
  Django's default SQL, so `db_functions` is not a supported module and its baseline
  is unknown.
- **Windows:** `supports_over_clause` is off; nothing is written yet.
- **JSON:** `capabilities.has_json_functions` exists: `JSON_OBJECT`, `JSON_VALUE` and
  `JSON_TABLE` worked in an early probe (IBMI_NOTES). There is no `JSONField` column type,
  `Value` refuses JSON, and 5.2 has one expected failure with `REASON_JSON_FIELD`.
- **Foreign keys:** `get_relations()` already returns the delete rule on 6.1
  (`compat.py`). The schema editor does not override the foreign key SQL, so Django 6.1's
  own template writes the rule (`%(on_delete_db)s`) once a model can use one; the flags
  are off, so none can.
- **Row locks:** `has_select_for_update` is off, so `select_for_update()` raises
  `NotSupportedError`.

## 2. Django test modules
Tests per module (`def test_` in `vendor/django-<version>/tests/<module>`):

| Module or label | 5.2 | 6.0 | 6.1 | Group | Note |
|---|---|---|---|---|---|
| `db_functions` | 315 | 315 | 323 | 1 | 3 tests need `has_json_object_function` |
| `expressions_window` | 75 | 75 | 75 | 2 | |
| `model_fields.test_jsonfield` | 97 | 102 | 129 | 3 | the whole of `model_fields` is 402 / 408 / 443 tests |
| `delete` (already supported) | 59 | 60 | 64 | 4 | the 6.1 tests of the rules come back on; also `schema`, `introspection`, `inspectdb` |
| `select_for_update` | 38 | 38 | 38 | 4 | uses a second connection: see the open questions |

**Step 0 measures each once on 6.1**, so the plan starts from real numbers, as in phase
5. Those runs have not happened, so this table holds test counts, not results. Tests
in supported modules that are skipped today because of these flags come back when a
flag goes on (`aggregation`, `annotations`, `expressions`, `queries`, `schema`,
`constraints`, `inspectdb`); the status run shows them.

## 3. Feature flags
The 26 flags with `planned` in [features.toml](../features.toml), all in phase 6.
"(not verified on IBM i)" marks an expectation that rests on IBM's documentation
only; "probe" names what decides. The results are in section 4.

| Group | Flag | Django | Expectation |
|---|---|---|---|
| 1 | `allows_group_by_lob` | all | probe `phase6_flags`; IBMI_NOTES has GROUP BY on LOB columns working (probe `queries`) |
| 1 | `rounds_to_even` | all | probe `db_functions`: expected off, if `ROUND` takes halves away from zero |
| 1 | `supports_cast_with_precision` | all | probe `db_functions`: on if `CAST` rounds as Django's test expects |
| 1 | `ignores_unnecessary_order_by_in_subqueries` | all | probe `phase6_flags`: stays off if an `ORDER BY` in a subquery is an error |
| 1 | `supports_aggregate_distinct_multiple_argument` | 6.0+ | on: `LISTAGG(DISTINCT ...)` with a separator worked (probe `listagg`) |
| 1 | `has_real_datatype` | all | on: `REAL` worked (probe `later_flags`); introspection has to map it |
| 1 | `supports_no_precision_decimalfield` | 6.1 | probe `phase6_flags`; intentionally off unless the driver can bind what `DECFLOAT(34)` takes |
| 2 | `supports_over_clause` | all | on: OLAP functions are documented (not verified on IBM i) |
| 2 | `supports_default_in_lead_lag` | all | on: documented (not verified on IBM i); the marker form decides |
| 2 | `supports_frame_range_fixed_distance` | all | on if `RANGE` with a number works: documented with one sort key (not verified on IBM i) |
| 2 | `supports_frame_exclusion` | all | off: `EXCLUDE` is not documented (not verified on IBM i) |
| 3 | `supports_json_field` | all | on, stored in a LOB: the probe's column type decides |
| 3 | `can_introspect_json_field` | all | off unless a `CHECK ... IS JSON` can be recognized (`lib_json_check`): `inspectdb` would see a plain LOB |
| 3 | `supports_primitives_in_json_field` | all | probe `json_functions`: scalars at the top level |
| 3 | `supports_json_field_contains` | all | expected off: no containment function is documented, as on Oracle (not verified on IBM i) |
| 3 | `supports_json_negative_indexing` | 6.0+ | probe `json_functions`: `[last-1]` or an error |
| 3 | `has_json_object_function` | all | on: `JSON_OBJECT` worked in an early probe; typed markers decide |
| 4 | `supports_on_delete_db_cascade` | 6.1 | on: documented (not verified on IBM i); `lib_on_delete` |
| 4 | `supports_on_delete_db_null` | 6.1 | on: documented (not verified on IBM i); `lib_on_delete` |
| 4 | `supports_on_delete_db_default` | 6.1 | on: documented (not verified on IBM i); `lib_on_delete` |
| 4 | `has_select_for_update` | all | **open question 1**: syntax by probe, the locks need more |
| 4 | `has_select_for_update_nowait` | all | probe `select_for_update` (no `NOWAIT` on IBM's update clause page) |
| 4 | `has_select_for_update_of` | all | probe `select_for_update` (`OF` names columns on IBM i, with a first-table restriction) |
| 4 | `select_for_update_of_column` | all | follows `has_select_for_update_of` |
| 4 | `has_select_for_update_skip_locked` | all | probe `select_for_update`: `SKIP LOCKED DATA` |
| 4 | `supports_select_for_update_with_limit` | all | probe `select_for_update` |

## 4. IBM i questions and probes

**QTEMP probes** (written, in `probes/`; each states where it acts and is published
with `bin/probe --publish`):

| Probe | Questions |
|---|---|
| `qtemp_window` | each window function; offsets, defaults and frames with constants, markers and typed markers; `RANGE` with numbers and dates; `EXCLUDE`, `GROUPS`; `FIRST_VALUE` over an `NCLOB`; a window in a subquery |
| `qtemp_json_functions` | `NCLOB`, `CLOB` CCSID 1208 and `BLOB` as the column; paths as literals and markers; quoted keys, array positions; a root array and scalars; JSON null against a missing key; `JSON_OBJECT` with typed markers; any way to do containment |
| `qtemp_db_functions` | Django's default SQL for each function against what Db2 for i takes; NULL arguments; non-ASCII text; hash encoding; how `ROUND` and `CAST` treat halves |
| `qtemp_select_for_update` | which locking statements are accepted (**syntax only**: it cannot show what they lock) |
| `qtemp_phase6_flags` | LOB in `GROUP BY`; `ORDER BY` in subqueries; `LISTAGG(DISTINCT)`; `DECFLOAT(34)` binding; `REAL` as the driver and the catalog see it |

**Results:** to be added when they have run. They wait for the status run: it holds
the PUB400 lock for all modules of a version.

**`lib_` probes** (not written, not run). Each is requested separately, saying what it
creates and how it cleans up, and runs only after the maintainer's approval comment:

| Probe | Why not QTEMP | What it does |
|---|---|---|
| `lib_on_delete` | constraints are refused in QTEMP (SQL7008) | two tables in the journaled library; a foreign key with each rule: what a parent delete does, what the catalog reports, whether both tables need the same journal |
| `lib_json_check` | the same | a `CHECK (c IS JSON)`: accepted, what it refuses, how it reads in the catalog |
| `lib_select_for_update` | needs commitment control | one job: after `FOR UPDATE` and after `USE AND KEEP EXCLUSIVE LOCKS`, does `QSYS2.RECORD_LOCK_INFO` show the row locks of the job? It cannot show a second job waiting |

**Not possible on PUB400:** anything with two connections. A second job waiting or
skipping locked rows joins `lib_merge_concurrency` on a dedicated IBM i.

## 5. Design
- **Functions:** an `as_db2_for_i` per function that differs from Django's SQL, in
  `expressions.py`, with typed markers as elsewhere. Any function Db2 for i cannot
  offer raises `NotSupportedError` and gets a fixed reason, not a workaround that could
  return different results.
- **Windows:** `Window` writes standard SQL, so most work is typed markers in its
  arguments, and `operations.window_frame_range_start_end()` if needed.
- **JSONField:**
  - **Column:** the type the probe proves, with a `CHECK ... IS JSON` if `lib_json_check`
    allows. A LOB means no `DISTINCT` and no index, as `TextField` has now.
  - **Lookups:** `as_db2_for_i` on `KeyTransform`, `HasKeyLookup` and the key lookups,
    like Django's Oracle code. If a path cannot be a marker it is inlined, escaped as
    Django's `compile_json_path` does for Oracle.
  - **Values:** `Value` gets its JSON rule, and `from_db_value` reads the LOB.
- **DB-level `on_delete`:** Django 6.1 writes the rule through `fk_on_delete_sql()` and its
  own foreign key template, so the work is mostly the flags, `lib_on_delete`'s findings
  and own tests. Any version difference stays in `compat.py`; 5.2 and 6.0 have no such
  rules.
- **Capabilities:** a feature that depends on the release or PTF level gets a capability
  (CLAUDE.md section 4); `has_json_functions` is already one.

## 6. Test strategy
- **Offline:** goldens per new SQL shape and Django series; unit tests for pure
  operations.
- **IBM i tests:** per flag, the real-world pattern: `Window` over a queryset with model
  instances; ranking with a partition; `Lag` with a default; a `JSONField` saved, read and
  filtered by key with non-ASCII text; `CASCADE` and `SET NULL` deleting real rows.
- **Django modules:** targeted runs while building, one IBM i cycle per PR.
- **Each core PR's cycle:** the full IBM i tests on 6.1 (about 23 minutes), `bin/verify` per
  Django version (about 35 minutes each) and the affected modules on all three. About
  2.5 hours, plus a repeat after any later core change, as #216 showed.

## 7. Plan with PR boundaries
**Four PRs** (the maintainer asked for few, because every core PR needs the full IBM i
run). Each keeps a commit per step, for review. Lowest risk first:

| PR | Content | Risk | Why this group |
|---|---|---|---|
| 0 | this plan, the probes and their results; a baseline on 6.1 | none: docs and probes | |
| 1 | **db functions and small flags**: the `as_db2_for_i` methods, `db_functions`, the 7 flags of group 1 | low to medium: many small methods, each isolated | failures stay inside one function; no new storage |
| 2 | **window functions**: group 2, `expressions_window` | low to medium: standard SQL | small; could join PR 1 if the baseline is nearly clean |
| 3 | **`JSONField`**: group 3, `model_fields.test_jsonfield` | **high** | **too risky to combine**: new column type, about 20 Django methods, and the most tests that change per version (97 to 129) |
| 4 | **DB-level `on_delete`** and, if question 1 allows, **row locks**: group 4 | medium; needs `lib_` probes | both wait for approvals, and neither touches PRs 1 to 3 |

**Where a group should not be combined:**
- **JSONField alone**, whatever happens to the others. If it fails it can wait without
  holding back anything else, and its 6.1 test set differs most.
- **Row locks may leave PR 4.** They are a correctness risk: a `select_for_update()` that
  does not lock would look fine in every test on PUB400. If question 1 is answered "off",
  PR 4 is `on_delete` only.
- **PRs 1 and 2 are the one safe merge.** It saves a cycle of about 2.5 hours, and I would
  decide from the baseline: combined if both are nearly clean, separate if `db_functions`
  shows many failures.

**Steps per commit in each PR:** the flag and implementation, Django tests with fixed
reasons, goldens, own IBM i test, then docs and changelog. Probes come before code, and a
`bin/verify` for each Django version runs on the PR's last code commit.

Close-out: the modules into `docs/status.toml`, a status run on all three versions, this
file rewritten as the record, as in phases 4 and 5.

## Open questions
1. **`select_for_update()`:** PUB400 allows one connection, so nothing can show a second
   job actually waiting. **Recommendation:** keep it off through phase 6 unless
   `lib_select_for_update` shows the row locks in the job's own lock list; even then,
   say plainly in Known Limitations that blocking was not tested. The alternative is on,
   from IBM's documentation alone, which is riskier for code that relies on the lock.
2. **`JSONField` column type:** decided by the probe. **Recommendation:** `NCLOB` if the
   JSON functions take it, because it is what `TextField` uses and is safe for all Unicode.
3. **`supports_no_precision_decimalfield` (6.1 only):** phase 6 if the probe shows a clean
   way to bind values, otherwise intentionally off. **Recommendation:** off unless it is
   clean; it needs a converter for one Django version only.
4. **`annotations` and `expressions_case` (#82):** not in this plan's scope, although
   they are near PR 1. **Recommendation:** leave them out unless PR 1's work fixes them.
5. **Whole `model_fields` or only `test_jsonfield`?** **Recommendation:** only the label,
   so the status run stays as short as possible; the other tests are about fields already
   covered elsewhere.
6. **Approval of the `lib_` probes** in section 4. Requested separately once this plan is
   approved.

## Links
- [features.toml](../features.toml): the flags `planned = "phase 6"`
- [phase-5.md](phase-5.md): "Carried forward"
- [IBM i 7.5: JSON_VALUE](https://www.ibm.com/docs/en/i/7.5?topic=functions-json-value),
  [OLAP specifications](https://www.ibm.com/docs/en/i/7.5?topic=expressions-olap-specifications),
  [update clause](https://www.ibm.com/docs/en/i/7.5?topic=statement-update-clause),
  [ALTER TABLE](https://www.ibm.com/docs/en/i/7.5?topic=statements-alter-table)
