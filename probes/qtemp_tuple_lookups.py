"""Probe 18: row-value predicates, as Django writes them with supports_tuple_lookups.

Read-only (VALUES only). With the flag on, Django renders lookups on a
multi-column relation or composite primary key as row values:
``(a, b) = (x, y)``, ``(a, b) IN ((x1, y1), ...)``, ``(a, b) > (x, y)``
(also >=, <, <=) and ``(a, b) IN (subquery)``; the right-hand side values are
parameter markers. Without the flag Django expands them (``a = x AND b = y``,
``a > x OR (a = x AND b > y)``, ...), which is the fallback the backend uses
today.

For each form: does Db2 for i accept it with untyped and with typed markers,
and do the rows of ``WHERE <form>`` and ``WHERE NOT (<form>)`` equal those of
the expanded form (three-valued logic, NULLs in either column)? Inside CASE
WHEN (XOR, a selected Q) the forms are recorded too. Comparisons against a
subquery (supports_tuple_comparison_against_subquery, a separate flag) are
only recorded. Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

NULLI = "CAST(NULL AS INTEGER)"
NULLV = "CAST(NULL AS VARCHAR(10))"
ROWS = (
    "(VALUES (1, 1, 'a'), (2, 1, 'b'), (3, 2, 'a'), (4, 1, "
    f"{NULLV}), (5, {NULLI}, 'a'), (6, {NULLI}, {NULLV}), (7, 3, 'c')) T (K, A, B)"
)
SUBQUERY = "SELECT X, Y FROM (VALUES (1, 'a'), (2, 'a')) S (X, Y)"
FIRST_ROW = "SELECT X, Y FROM (VALUES (1, 'b')) S (X, Y)"
UNTYPED = ("?", "?")
TYPED = ("CAST(? AS INTEGER)", "CAST(? AS VARCHAR(10))")

# (label, row-value form, expanded form, params of one form)
FORMS: list[tuple[str, str, str, tuple]] = []
for kind, (x, y) in (("untyped", UNTYPED), ("typed", TYPED)):
    FORMS += [
        (f"= ({kind})", f"(T.A, T.B) = ({x}, {y})", f"T.A = {x} AND T.B = {y}", (1, "a")),
        (
            f"<> ({kind})",
            f"(T.A, T.B) <> ({x}, {y})",
            f"NOT (T.A = {x} AND T.B = {y})",
            (1, "a"),
        ),
        (
            f"IN list ({kind})",
            f"(T.A, T.B) IN (({x}, {y}), ({x}, {y}))",
            f"(T.A = {x} AND T.B = {y}) OR (T.A = {x} AND T.B = {y})",
            (1, "a", 2, "a"),
        ),
        (
            f"> ({kind})",
            f"(T.A, T.B) > ({x}, {y})",
            f"T.A > {x} OR (T.A = {x} AND T.B > {y})",
            (1, "a"),
        ),
        (
            f">= ({kind})",
            f"(T.A, T.B) >= ({x}, {y})",
            f"T.A > {x} OR (T.A = {x} AND T.B >= {y})",
            (1, "a"),
        ),
        (
            f"< ({kind})",
            f"(T.A, T.B) < ({x}, {y})",
            f"T.A < {x} OR (T.A = {x} AND T.B < {y})",
            (2, "a"),
        ),
        (
            f"<= ({kind})",
            f"(T.A, T.B) <= ({x}, {y})",
            f"T.A < {x} OR (T.A = {x} AND T.B <= {y})",
            (2, "a"),
        ),
    ]
FORMS.append(
    (
        "IN (subquery)",
        f"(T.A, T.B) IN ({SUBQUERY})",
        f"EXISTS (SELECT 1 FROM ({SUBQUERY}) Q (X, Y) WHERE T.A = Q.X AND T.B = Q.Y)",
        (),
    )
)

_SQLCODE = re.compile(r"\((-?\d+)\)")


def _expanded_params(label: str, params: tuple) -> tuple:
    """The expanded forms repeat the first column's marker (> / >= / < / <=)."""
    if label.startswith((">", "<")) and not label.startswith("<>"):
        return (params[0], params[0], params[1])
    return params


def keys(conn, sql: str, params: tuple) -> Any:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return [tuple(row) for row in cursor.fetchall()]
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        return f"error {code.group(1) if code else exc.args[0]}"
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, form, expanded, params in FORMS:
        eparams = _expanded_params(label, params)
        native = keys(conn, f"SELECT K FROM {ROWS} WHERE {form} ORDER BY K", params)
        native_not = keys(conn, f"SELECT K FROM {ROWS} WHERE NOT ({form}) ORDER BY K", params)
        fallback = keys(conn, f"SELECT K FROM {ROWS} WHERE {expanded} ORDER BY K", eparams)
        fallback_not = keys(
            conn, f"SELECT K FROM {ROWS} WHERE NOT ({expanded}) ORDER BY K", eparams
        )
        case = keys(
            conn,
            f"SELECT K, CASE WHEN {form} THEN 1 WHEN NOT ({form}) THEN 0 END "
            f"FROM {ROWS} ORDER BY K",
            params + params,
        )
        outcome = {
            "rows (row value / expanded)": f"{native} / {fallback}",
            "NOT rows (row value / expanded)": f"{native_not} / {fallback_not}",
            "CASE WHEN (1 true, 0 false, None unknown)": f"{case}",
            "verdict": "same"
            if isinstance(native, list) and native == fallback and native_not == fallback_not
            else "DIFFERENT",
        }
        results[label] = outcome
        print(f"\n  {label}")
        for key, value in outcome.items():
            print(f"    {key:<42} {value}")
    # supports_tuple_comparison_against_subquery (separate flag): record only.
    for label, sql in (
        ("= (subquery)", f"SELECT K FROM {ROWS} WHERE (T.A, T.B) = ({FIRST_ROW}) ORDER BY K"),
        ("> (subquery)", f"SELECT K FROM {ROWS} WHERE (T.A, T.B) > ({FIRST_ROW}) ORDER BY K"),
    ):
        results[label] = keys(conn, sql, ())
        print(f"\n  {label:<44} {results[label]}")
    return results
