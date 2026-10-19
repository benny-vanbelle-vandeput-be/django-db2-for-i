"""Probe 14: data mapping errors in the select list (silent NULL?).

Read-only (SYSDUMMY1). On Db2 for i, ``SELECT CAST('abc' AS INTEGER)`` and a
division by zero in the select list return NULL instead of an error (probe
fetch_errors). This probe checks whether the driver reports a warning
(SQL_SUCCESS_WITH_INFO, visible in pyodbc's ``cursor.messages``) at execute
or at fetch, with the backend's connection attributes. Findings go to
docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings

NEEDS_CONNECTION = True
AUTOCOMMIT = True
BACKEND = {"CMT": "1", "TRUEAUTOCOMMIT": "1", "NAM": "0", "DFT": "5", "TFT": "2"}

CHECKS = [
    ("cast 'abc' to INTEGER", "SELECT CAST('abc' AS INTEGER) FROM SYSIBM.SYSDUMMY1", ()),
    (
        "cast of a parameter",
        "SELECT CAST(CAST(? AS VARCHAR(3)) AS INTEGER) FROM SYSIBM.SYSDUMMY1",
        ("abc",),
    ),
    (
        "division by zero",
        "SELECT 1 / (SELECT COUNT(*) - 1 FROM SYSIBM.SYSDUMMY1) FROM SYSIBM.SYSDUMMY1",
        (),
    ),
    (
        "one bad row of three",
        "SELECT V, CAST(V AS INTEGER) FROM (VALUES '1', 'x', '3') T (V) ORDER BY V",
        (),
    ),
    ("valid cast (no warning expected)", "SELECT CAST('12' AS INTEGER) FROM SYSIBM.SYSDUMMY1", ()),
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, sql, params in CHECKS:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params) if params else cursor.execute(sql)
            after_execute = list(cursor.messages)
            rows = [tuple(row) for row in cursor.fetchall()]
            after_fetch = list(cursor.messages)
            outcome = {
                "rows": rows,
                "messages after execute": after_execute or "none",
                "messages after fetch": after_fetch or "none",
            }
        finally:
            cursor.close()
        results[label] = outcome
        print(f"\n  {label}")
        for key, value in outcome.items():
            print(f"    {key:<24} {value}")
    return results
