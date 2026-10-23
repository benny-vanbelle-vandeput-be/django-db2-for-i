"""Probe 19: ordered and sliced parts of compound queries, in parentheses.

Read-only (VALUES only). With ``supports_slicing_ordering_in_compound`` and
``supports_parentheses_in_compound``, Django writes each part of a UNION /
INTERSECT / EXCEPT in parentheses, with its own ORDER BY and OFFSET / FETCH
FIRST, also when the compound query is a subquery, and a nested compound
query as a parenthesised part. Probe 9 covered parenthesised top-level parts
with ORDER BY + FETCH FIRST / OFFSET; this probe checks the remaining shapes.
Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

D = "FROM SYSIBM.SYSDUMMY1"
NULLI = "CAST(NULL AS INTEGER)"
# K: key, X: value with a NULL, Y: a column that is not selected.
T = f"(VALUES (1, 3, 30), (2, 1, 10), (3, {NULLI}, 20), (4, 2, 40)) T (K, X, Y)"
OUTER = "(VALUES 1, 2, 3, 4) O (K)"

# (label, sql, params, expected rows or None to only record)
CHECKS: list[tuple[str, str, tuple, Any]] = [
    (
        "part: ORDER BY with NULL ordering emulation + FETCH FIRST",
        f"(SELECT X FROM {T} ORDER BY X IS NULL, X ASC FETCH FIRST 2 ROWS ONLY) "
        f"UNION (SELECT 9 {D}) ORDER BY 1",
        (),
        [(1,), (2,), (9,)],
    ),
    (
        "part: ORDER BY a column that is not selected + FETCH FIRST",
        f"(SELECT X FROM {T} ORDER BY Y DESC FETCH FIRST 1 ROWS ONLY) "
        f"UNION (SELECT 9 {D}) ORDER BY 1",
        (),
        [(2,), (9,)],
    ),
    (
        "part: ORDER BY without FETCH FIRST",
        f"(SELECT X FROM {T} WHERE X IS NOT NULL ORDER BY X) UNION (SELECT 9 {D}) ORDER BY 1",
        (),
        [(1,), (2,), (3,), (9,)],
    ),
    (
        "parts with markers, OFFSET and FETCH FIRST",
        f"(SELECT X FROM {T} WHERE X > CAST(? AS INTEGER) ORDER BY X "
        "OFFSET 1 ROWS FETCH FIRST 1 ROWS ONLY) "
        f"UNION ALL (SELECT CAST(? AS INTEGER) {D}) ORDER BY 1",
        (0, 9),
        [(2,), (9,)],
    ),
    (
        "parenthesised parts, FETCH FIRST after the compound",
        f"(SELECT X FROM {T} WHERE X IS NOT NULL) UNION (SELECT 9 {D}) "
        "ORDER BY 1 DESC FETCH FIRST 2 ROWS ONLY",
        (),
        [(9,), (3,)],
    ),
    (
        "nested compound as a parenthesised part",
        f"(SELECT X FROM {T} WHERE X IS NOT NULL UNION SELECT 9 {D}) "
        f"INTERSECT (SELECT 9 {D}) ORDER BY 1",
        (),
        [(9,)],
    ),
    (
        "nested compound with parenthesised parts inside",
        f"((SELECT X FROM {T} ORDER BY X DESC FETCH FIRST 1 ROWS ONLY) UNION (SELECT 9 {D})) "
        f"EXCEPT (SELECT 9 {D}) ORDER BY 1",
        (),
        [(None,)],  # DESC puts NULL first (NULLs sort as the largest value)
    ),
    (
        "subquery: IN ((part) UNION (part)) with sliced parts",
        f"SELECT K FROM {OUTER} WHERE O.K IN ((SELECT X FROM {T} ORDER BY X FETCH FIRST 1 ROWS "
        f"ONLY) UNION (SELECT 4 {D})) ORDER BY K",
        (),
        [(1,), (4,)],
    ),
    (
        "subquery: scalar ((part) UNION (part)) as a select column",
        f"SELECT K, ((SELECT X FROM {T} WHERE T.K = O.K) UNION (SELECT 0 {D} WHERE 1 = 0)) "
        f"FROM {OUTER} ORDER BY K",
        (),
        [(1, 3), (2, 1), (3, None), (4, 2)],
    ),
    (
        "subquery: EXISTS ((part) UNION (part))",
        f"SELECT K FROM {OUTER} WHERE EXISTS ((SELECT 1 {D} WHERE O.K = 1) "
        f"UNION (SELECT 1 {D} WHERE O.K = 3)) ORDER BY K",
        (),
        [(1,), (3,)],
    ),
    (
        "subquery: LATERAL wrapper around parenthesised parts, correlated",
        f"SELECT K, (SELECT * FROM LATERAL ((SELECT X FROM {T} WHERE T.K = O.K) "
        f"UNION (SELECT 9 {D})) AS U ORDER BY 1 FETCH FIRST 1 ROWS ONLY) "
        f"FROM {OUTER} ORDER BY K",
        (),
        [(1, 3), (2, 1), (3, 9), (4, 2)],
    ),
    (
        "subquery: correlated sliced part inside IN",
        f"SELECT K FROM {OUTER} WHERE O.K IN ((SELECT K FROM {T} WHERE T.Y > O.K * 10 "
        f"ORDER BY Y FETCH FIRST 1 ROWS ONLY) UNION (SELECT 0 {D})) ORDER BY K",
        (),
        [],  # the first K by Y above O.K * 10 is never O.K itself
    ),
    (
        "top level: SELECT * FROM LATERAL ((part) UNION (part)) ORDER BY expression",
        f"SELECT * FROM LATERAL ((SELECT X FROM {T} ORDER BY Y FETCH FIRST 3 ROWS ONLY) "
        f"UNION (SELECT 9 {D})) AS U ORDER BY X IS NULL, X",
        (),
        [(1,), (3,), (9,), (None,)],
    ),
]

_SQLCODE = re.compile(r"\((-?\d+)\)")


def rows(conn, sql: str, params: tuple) -> Any:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return [tuple(row) for row in cursor.fetchall()]
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        text = re.sub(r"^(\[[^\]]*\]\s*)+", "", message)
        return f"error {code.group(1) if code else exc.args[0]}: {text[:80]}"
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, sql, params, expected in CHECKS:
        got = rows(conn, sql, params)
        if expected is None:
            verdict = "recorded"
        else:
            verdict = "ok" if got == expected else f"UNEXPECTED (want {expected})"
        results[label] = {"rows": got, "verdict": verdict}
        print(f"  {label:<72} {verdict}: {got}")
    return results
