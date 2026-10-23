"""Probe 17: tuple IN (subquery), and a rewrite for any number of columns.

Read-only (VALUES only). Django filters a multi-column relation
(ForeignObject) with ``(a, b) IN (subquery)``. Outside a search condition
(XOR, a selected Q) IN (subquery) needs the rewrite of probe 16, which only
handled one column. The general form, for columns x1..xn and subquery
columns V1..Vn:

- TRUE if a row matches on every column;
- else NULL if a row has no column that is definitely unequal (each column
  equal, or NULL on either side);
- else FALSE (also for an empty subquery).

For each subquery the rows of ``WHERE <rewrite>`` and ``WHERE NOT
<rewrite>`` must equal those of plain IN / NOT IN, and CASE WHEN must give 1
exactly where IN (or NOT IN) is true. One column (probe 16's data) checks
that the general form also replaces the single-column one.
Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

NULL = "CAST(NULL AS INTEGER)"
PAIRS = f"(VALUES (1, 1, 1), (2, 1, {NULL}), (3, {NULL}, {NULL}), (4, 2, 2), (5, 3, 9)) T (K, A, B)"
SINGLES = f"(VALUES (1, 1), (2, 2), (3, 3), (4, {NULL})) T (K, A)"
PAIR_SUBQUERIES = {
    "match and a partly NULL row": f"SELECT V1, V2 FROM (VALUES (1, 1), (3, {NULL})) Q (V1, V2)",
    "no NULL": "SELECT V1, V2 FROM (VALUES (2, 2)) Q (V1, V2)",
    "only (NULL, NULL)": f"SELECT V1, V2 FROM (VALUES ({NULL}, {NULL})) Q (V1, V2)",
    "(1, NULL)": f"SELECT V1, V2 FROM (VALUES (1, {NULL})) Q (V1, V2)",
    "empty": "SELECT V1, V2 FROM (VALUES (1, 1)) Q (V1, V2) WHERE V1 = 0",
}
SINGLE_SUBQUERIES = {
    "match and NULL": f"SELECT V1 FROM (VALUES 1, {NULL}) Q (V1)",
    "no NULL": "SELECT V1 FROM (VALUES 2) Q (V1)",
    "only NULL": f"SELECT V1 FROM (VALUES {NULL}) Q (V1)",
    "empty": "SELECT V1 FROM (VALUES 1) Q (V1) WHERE V1 = 0",
}
_SQLCODE = re.compile(r"\((-?\d+)\)")


def rewrite(xs: list[str], subquery: str) -> str:
    """The general three-valued form, compared with TRUE."""
    names = [f"V{i}" for i in range(1, len(xs) + 1)]
    lateral = f"LATERAL ({subquery}) AS S ({', '.join(names)})"
    equal = " AND ".join(f"S.{v} = {x}" for v, x in zip(names, xs, strict=True))
    maybe = " AND ".join(
        f"(S.{v} = {x} OR S.{v} IS NULL OR {x} IS NULL)" for v, x in zip(names, xs, strict=True)
    )
    match = f"(SELECT 1 FROM {lateral} WHERE {equal} FETCH FIRST 1 ROWS ONLY)"
    unknown = f"(SELECT 1 FROM {lateral} WHERE {maybe} FETCH FIRST 1 ROWS ONLY)"
    return (
        f"(CASE WHEN {match} IS NOT NULL THEN TRUE "
        f"WHEN {unknown} IS NOT NULL THEN NULL ELSE FALSE END) = TRUE"
    )


def keys(conn, sql: str) -> Any:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return [tuple(row) for row in cursor.fetchall()]
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        return f"error {code.group(1) if code else exc.args[0]}"
    finally:
        cursor.close()


def compare(conn, table: str, xs: list[str], subquery: str, ks: range) -> dict[str, str]:
    lhs = xs[0] if len(xs) == 1 else f"({', '.join(xs)})"
    form = rewrite(xs, subquery)
    plain_in = keys(conn, f"SELECT K FROM {table} WHERE {lhs} IN ({subquery}) ORDER BY K")
    plain_not = keys(conn, f"SELECT K FROM {table} WHERE {lhs} NOT IN ({subquery}) ORDER BY K")
    new_in = keys(conn, f"SELECT K FROM {table} WHERE {form} ORDER BY K")
    new_not = keys(conn, f"SELECT K FROM {table} WHERE NOT ({form}) ORDER BY K")
    case = keys(
        conn,
        f"SELECT K, CASE WHEN {form} THEN 1 ELSE 0 END, "
        f"CASE WHEN NOT ({form}) THEN 1 ELSE 0 END FROM {table} ORDER BY K",
    )
    want_case = (
        [(k, int((k,) in plain_in), int((k,) in plain_not)) for k in ks]
        if isinstance(plain_in, list) and isinstance(plain_not, list)
        else None
    )
    return {
        "IN rows (plain / rewrite)": f"{plain_in} / {new_in}",
        "NOT IN rows (plain / rewrite)": f"{plain_not} / {new_not}",
        "CASE WHEN (positive, negated)": f"{case}",
        "verdict": "same"
        if plain_in == new_in and plain_not == new_not and case == want_case
        else "DIFFERENT",
    }


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    cases = [
        (f"pairs, {label}", PAIRS, ["T.A", "T.B"], subquery, range(1, 6))
        for label, subquery in PAIR_SUBQUERIES.items()
    ] + [
        (f"one column, {label}", SINGLES, ["T.A"], subquery, range(1, 5))
        for label, subquery in SINGLE_SUBQUERIES.items()
    ]
    for label, table, xs, subquery, ks in cases:
        outcome = compare(conn, table, xs, subquery, ks)
        results[label] = outcome
        print(f"\n  {label}")
        for key, value in outcome.items():
            print(f"    {key:<32} {value}")
    return results
