"""Probe 16: IN (subquery) outside a search condition, and its rewrite.

Read-only (VALUES only). Db2 for i rejects ``x IN (subquery)`` and ``x = ANY
(subquery)`` inside CASE WHEN (SQL0115), which Django's XOR emulation
produces. The rewrite must keep SQL's three-valued logic exactly, also when
negated: for each x (1, 2, 3, NULL) and each subquery (a match plus a NULL,
no NULL, only a NULL, empty), the rows of ``WHERE <rewrite>`` and ``WHERE
NOT <rewrite>`` must equal those of plain ``WHERE x IN`` / ``WHERE x NOT
IN``, and CASE WHEN must give 1 exactly for the rows where IN is true.
Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

XS = "(VALUES (1, 1), (2, 2), (3, 3), (4, CAST(NULL AS INTEGER))) T (K, X)"
SUBQUERIES = {
    "match and NULL": "SELECT V FROM (VALUES 1, CAST(NULL AS INTEGER)) Q (V)",
    "no NULL": "SELECT V FROM (VALUES 2) Q (V)",
    "only NULL": "SELECT V FROM (VALUES CAST(NULL AS INTEGER)) Q (V)",
    "empty": "SELECT V FROM (VALUES 1) Q (V) WHERE V = 0",
}
_SQLCODE = re.compile(r"\((-?\d+)\)")


def rewrite(x: str, subquery: str) -> str:
    """The backend's form: a three-valued BOOLEAN compared with TRUE."""
    lateral = f"LATERAL ({subquery}) AS S (V)"
    match = f"(SELECT 1 FROM {lateral} WHERE S.V = {x} FETCH FIRST 1 ROWS ONLY)"
    any_row = f"(SELECT 1 FROM {lateral} FETCH FIRST 1 ROWS ONLY)"
    null_row = f"(SELECT 1 FROM {lateral} WHERE S.V IS NULL FETCH FIRST 1 ROWS ONLY)"
    return (
        f"(CASE WHEN {match} IS NOT NULL THEN TRUE WHEN {any_row} IS NULL THEN FALSE "
        f"WHEN {x} IS NULL THEN NULL WHEN {null_row} IS NOT NULL THEN NULL ELSE FALSE END) = TRUE"
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


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, subquery in SUBQUERIES.items():
        form = rewrite("T.X", subquery)
        plain_in = keys(conn, f"SELECT K FROM {XS} WHERE T.X IN ({subquery}) ORDER BY K")
        plain_not = keys(conn, f"SELECT K FROM {XS} WHERE T.X NOT IN ({subquery}) ORDER BY K")
        new_in = keys(conn, f"SELECT K FROM {XS} WHERE {form} ORDER BY K")
        new_not = keys(conn, f"SELECT K FROM {XS} WHERE NOT ({form}) ORDER BY K")
        case = keys(
            conn,
            f"SELECT K, CASE WHEN {form} THEN 1 ELSE 0 END, "
            f"CASE WHEN NOT ({form}) THEN 1 ELSE 0 END FROM {XS} ORDER BY K",
        )
        want_case = (
            [(k, int((k,) in plain_in), int((k,) in plain_not)) for k in (1, 2, 3, 4)]
            if isinstance(plain_in, list) and isinstance(plain_not, list)
            else None
        )
        outcome = {
            "IN rows (plain / rewrite)": f"{plain_in} / {new_in}",
            "NOT IN rows (plain / rewrite)": f"{plain_not} / {new_not}",
            "CASE WHEN (positive, negated)": f"{case}",
            "verdict": "same"
            if plain_in == new_in and plain_not == new_not and case == want_case
            else "DIFFERENT",
        }
        results[label] = outcome
        print(f"\n  subquery: {label}")
        for key, value in outcome.items():
            print(f"    {key:<32} {value}")
    return results
