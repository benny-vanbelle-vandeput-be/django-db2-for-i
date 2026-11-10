# Phase 6: Advanced

> Status: Done (2026-11-05)

## Goal
From CLAUDE.md section 9: **advanced**: window functions, `JSONField`, db
functions, DB-level `on_delete` (6.1+), plus the flags moved to phase 6 earlier
(#191, topic 3; the phase 2 query flags). The row locks of `select_for_update()`
wait for a dedicated IBM i (answer 1).

"Done when" (approved), all met:
- The Django modules `db_functions` and `expressions_window` and the label
  `model_fields.test_jsonfield` run on 6.1, 6.0 and 5.2 against PUB400 without
  failures or errors, every remaining failure a skip or expected failure with one
  fixed reason, and they join the supported modules. The DB-level `on_delete`
  tests in `delete` and `schema` do the same on 6.1.
- No flag is `planned = "phase 6"` in [features.toml](../features.toml): each is on
  with an own IBM i test of the real-world pattern, or off with a reason; the row
  locks are planned for a dedicated IBM i.
- Goldens for every new SQL shape, per Django series, all verified on PUB400.
- The probe results decisions rest on are in IBMI_NOTES and `probes/results/`.
- Known Limitations states what users must know, in the same pull request as each
  change.

## What was done
**All of phase 6 in one pull request,
[#227](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/227)**, a
commit or a small set per step (the maintainer's change of plan, 2026-11-04, below).

**Step 0: plan, probes, `lib_` probes**
- The plan ([#218](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/218)),
  the QTEMP probes `qtemp_window`, `qtemp_json_functions`, `qtemp_db_functions`,
  `qtemp_select_for_update`, `qtemp_phase6_flags`, `qtemp_json_errors`, and the
  approved `lib_on_delete` ([#220](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/220))
  and `lib_json_check` ([#221](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/221))
  ([#223](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/223)).

**Step 1: db functions and the group 1 flags**
- An `as_db2_for_i` per function that differs: `Length` (`CHARACTER_LENGTH`), `Log`
  (`LN(b) / LN(a)`), `Concat` (NULL as empty text), `ATan2` (arguments swapped),
  `MD5` / `SHA1` / `SHA256` / `SHA512` (`HASH_*` over UTF-8), typed NULLs for
  `LPad`, `RPad`, `Repeat`. `Cast` to a decimal rounds (through `DECFLOAT(34)` for a
  float), and `Cast` of a float to text goes through `DECFLOAT(16) + 0` (`3`, not
  `3E0`). `Reverse`, `SHA224`, `SHA384` raise `NotSupportedError`.
- On: `allows_group_by_lob`, `ignores_unnecessary_order_by_in_subqueries`,
  `supports_aggregate_distinct_multiple_argument` (6.0+), `supports_cast_with_precision`,
  `has_real_datatype`. Off: `rounds_to_even`, `supports_no_precision_decimalfield`.
- Probes `qtemp_db_function_args`, `qtemp_float_text`.

**Step 2: window functions**
- `supports_over_clause`, `supports_default_in_lead_lag`,
  `supports_frame_range_fixed_distance`; `supports_frame_exclusion` off. A `LAG` /
  `LEAD` offset and `NTH_VALUE`'s position are literals; `PERCENT_RANK` and
  `CUME_DIST` cast to DOUBLE.

**Step 3: DB-level `on_delete`** (Django 6.1)
- `supports_on_delete_db_cascade`, `supports_on_delete_db_null`,
  `supports_on_delete_db_default`. Django writes the clause through its own
  template; `lib_on_delete` showed that each rule works as IBM documents.

**Step 4: `JSONField`**
- `supports_json_field` and `has_json_object_function` (capability
  `has_json_functions`). An `NCLOB`; key lookups through `JSON_QUERY` (paths as
  literals, keys raw, a marker above U+FFFE), `has_key` / `isnull` through
  `JSON_EXISTS`, right-hand sides normalized through `JSON_OBJECT(... FORMAT JSON)`,
  numeric comparisons through `JSON_VALUE ... DECFLOAT(34)`, and `JSONObject` /
  `JSONArray` as `JSON_OBJECT` / `JSON_ARRAY ... NULL ON NULL RETURNING NCLOB(1M)`.
  Off: `can_introspect_json_field`, `supports_primitives_in_json_field` (open
  question 7: the functions cannot reach a root scalar),
  `supports_json_field_contains`, `supports_json_negative_indexing`.
- Probe `qtemp_json_lookups`, extended twice: key escaping, then the forms the first
  final cycle needed.

**Tooling:** `bin/verify --full-own-done-on <version>`, so that a cycle over several
Django versions runs the full own IBM i tier once.

**Close-out**
- This record; `db_functions`, `expressions_window` and the
  `model_fields.test_jsonfield` label in `docs/status.toml`; the status run on all
  three versions, which found two defects, each fixed in its own pull request: the
  corpus capture hook ran a QuerySet a query held
  ([#229](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/229)),
  and a `CASE` with only bare NULL results had no type
  ([#230](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/230)).
  Three of its runs lost the connection to PUB400 (`08S01`, `CWBCO1034`) and one
  was cut off by a reboot; they were run again and passed, without a change.

## Key decisions
- **The plan's answers** (2026-11-01, [#218](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/pull/218)):
  row locks off as an open track for a dedicated IBM i; `JSONField` an `NCLOB`, with
  error clauses only where Django expects an error (none turned out to be needed);
  `supports_no_precision_decimalfield` intentionally off; #82 out of the phase.
- **One pull request for the phase** (maintainer, 2026-11-04, because of PUB400's
  speed): targeted runs on 6.1 while building, one final cycle on all three
  versions: [DECISIONS](../DECISIONS.md#2026-11-04-phase-6-in-one-pr-targeted-runs-on-61-while-building-one-final-cycle).
  The `JSONField` commits stayed in it.
- **The first final cycle was stopped** (on `a4031b3`): it found failures the
  targeted runs had missed, and a fix in `expressions.py` makes a cycle invalid, so
  the whole cycle ran again on `1e75b78`.

## IBM i findings
Details in IBMI_NOTES ([phase 6 probes](../IBMI_NOTES.md#phase-6-probes-window-functions-json-db-functions-row-locks)).
- A DOUBLE as text is exponent notation; `DECFLOAT(16) + 0` gives Django's form,
  with 16 significant digits.
- `ROUND` takes halves away from zero, `CAST` cuts off, and `ROUND` of a DOUBLE stays
  binary.
- A JSON path reads no JSON escapes; an emoji or U+FFFF in a path literal is lost in
  the statement (a marker works); a key with a double quote cannot be written.
  `JSON_QUERY` returns a `CLOB`, which `LISTAGG` refuses with an `NVARCHAR` separator.
- A JSON function is refused in a `CHECK` (SQL0546) and in an index expression
  (SQL0356).

## Test status at the end of the phase
The final cycle on `1e75b78` (#227), PUB400 (IBM i 7.5), Python 3.14, `--clean`,
2026-11-05:

| Module | Django 6.1 | Django 6.0 | Django 5.2 | Baseline on 6.1 |
|---|---|---|---|---|
| `db_functions` | 371: 31 skipped, 18 expected failures | 363: 26 skipped, 18 expected failures | 363: 26 skipped, 18 expected failures | 23 failures, 63 errors |
| `expressions_window` | 75: 9 skipped | 75: 9 skipped | 75: 9 skipped | all skipped (flags off) |
| `model_fields.test_jsonfield` | 129: 37 skipped, 4 expected failures | 102: 14 skipped, 4 expected failures | 97: 11 skipped, 4 expected failures | all skipped (flags off) |

0 failures and 0 errors in each; also in `aggregation`, `expressions` and `delete` on
all three, and `schema`, `introspection` and `inspectdb` on 6.1. The own IBM i tests
on 6.1: 416 passed, 1 expected failure. The whole `model_fields` module, measured once
for information (answer 5), on 6.1 on 2026-11-10 (PUB400, `--clean`): 570 tests,
129 skipped, 4 expected failures, **2 failures**, 0 errors. Both have known causes;
neither is a new defect:

- `test_datetimefield.DateTimeFieldTests.test_datetimes_save_completely`: a
  `TimeField` loses its microseconds (Db2 for i `TIME` has no fractional seconds;
  `REASON_TIME_FRACTIONS`, Known Limitations).
- `tests.BasicFieldTests.test_get_placeholder_sql_shim`: the test compares the exact
  SQL `(1 + %s)`; the backend types the parameter marker (`CAST(%s AS INTEGER)`).

Only the `test_jsonfield` label is supported; the rest of `model_fields` can join
the supported modules once these two are on the lists with their reasons (a later
pull request). The complete status comes from the close-out's status run on
`ecbec96` (5.2, 6.0 and 6.1, 29 runs each, all passed): [TEST_STATUS](../TEST_STATUS.md).

## Carried forward
- **Row locks** (`select_for_update`, 6 flags): a dedicated IBM i, two connections.
- **`lib_merge_concurrency`** (from phase 5): the same.
- **DB-level `on_delete` across differently journaled libraries:** not tested.
- **Limitations that stay** ([Known limitations](../user/Known-Limitations.md)): JSON
  keys with a double quote, ordering by a JSON key as text, no index or `CHECK` on a
  JSON key, no `contains`, no negative indexes, no lookups on a root scalar;
  `Reverse`, `SHA224`, `SHA384`; `Chr` / `Ord` beyond ASCII; window frames with
  `exclusion` or a fixed `RANGE` over dates; a float as text with 16 digits.
- **Phase 7**: the PUB400 tier and release preparation.
- **Open issues:** [#82](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/82),
  [#95](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/95),
  [#124](https://github.com/benny-vanbelle-vandeput-be/django-db2-for-i/issues/124).

## Links
- [DJANGO_VERSIONS.md](../DJANGO_VERSIONS.md), [FEATURES.md](../FEATURES.md),
  [TEST_STATUS.md](../TEST_STATUS.md), [Known limitations](../user/Known-Limitations.md).
- Changelog: the fragments in `changelog.d/` until the next release.
- The approved plan: this file from the merge of #218 until this close-out.
