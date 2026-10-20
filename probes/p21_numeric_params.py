"""Probe 21: numeric filter values that do not fit the column, as typed markers.

Writes only to QTEMP (a table that disappears with the job). Issue #69: an
untyped marker is sized by the column, so an integer out of a SMALLINT's
range in an IN list or a BETWEEN, or a Decimal with more digits than
DECIMAL(p, s), fails in the driver (30018 / 30160 / 30126). The candidate
fix types such a marker by the value itself, ``CAST(? AS DECIMAL(p', s'))``.
This probe checks, with the backend's connection attributes, that Db2 for i
then compares exactly: rows holding the truncated (1.00) and the rounded
(1.01) value of 1.005 must never match, and =, <>, <, >, IN, NOT IN and
BETWEEN must give exactly the rows of exact arithmetic. Also: exponent
forms, -0, integers beyond BIGINT, and the DECIMAL precision limit.

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True
AUTOCOMMIT = True
BACKEND = {"CMT": "1", "TRUEAUTOCOMMIT": "1", "NAM": "0", "DFT": "5", "TFT": "2"}
_SQLCODE = re.compile(r"\((-?\d+)\)")

# K, SMALL (SMALLINT), AMOUNT (DECIMAL(5, 2))
ROWS = [
    (1, 1, Decimal("1.00")),  # 1.005 truncated
    (2, 32767, Decimal("1.01")),  # 1.005 rounded half up
    (3, -32768, Decimal("999.99")),
    (4, 0, Decimal("-1.00")),
    (5, None, None),
    (6, 2, Decimal("0.00")),
]
T = "QTEMP.P21"
D43 = "CAST(? AS DECIMAL(4, 3))"
D60 = "CAST(? AS DECIMAL(6, 0))"

# (label, WHERE clause, params, expected keys or None to only record)
CHECKS: list[tuple[str, str, tuple, Any]] = [
    ("AMOUNT = typed 1.005", f"AMOUNT = {D43}", (Decimal("1.005"),), []),
    ("AMOUNT <> typed 1.005", f"AMOUNT <> {D43}", (Decimal("1.005"),), [1, 2, 3, 4, 6]),
    ("AMOUNT > typed 1.005", f"AMOUNT > {D43}", (Decimal("1.005"),), [2, 3]),
    ("AMOUNT < typed 1.005", f"AMOUNT < {D43}", (Decimal("1.005"),), [1, 4, 6]),
    (
        "AMOUNT IN (untyped 0.00, typed 1.005)",
        f"AMOUNT IN (?, {D43})",
        (Decimal("0.00"), Decimal("1.005")),
        [6],
    ),
    (
        "AMOUNT NOT IN (untyped 0.00, typed 1.005)",
        f"AMOUNT NOT IN (?, {D43})",
        (Decimal("0.00"), Decimal("1.005")),
        [1, 2, 3, 4],
    ),
    (
        "AMOUNT BETWEEN typed 0.995 AND typed 1.005",
        f"AMOUNT BETWEEN {D43} AND {D43}",
        (Decimal("0.995"), Decimal("1.005")),
        [1],
    ),
    (
        "AMOUNT = typed 123456.789",
        "AMOUNT = CAST(? AS DECIMAL(9, 3))",
        (Decimal("123456.789"),),
        [],
    ),
    (
        "AMOUNT < typed 123456.789",
        "AMOUNT < CAST(? AS DECIMAL(9, 3))",
        (Decimal("123456.789"),),
        [1, 2, 3, 4, 6],
    ),
    (
        "AMOUNT = typed -0.0 (DECIMAL(2, 1))",
        "AMOUNT = CAST(? AS DECIMAL(2, 1))",
        (Decimal("-0.0"),),
        [6],
    ),
    ("AMOUNT = typed 1E+5 (DECIMAL(6, 0))", f"AMOUNT = {D60}", (Decimal("1E+5"),), []),
    ("AMOUNT < typed 1E+5 (DECIMAL(6, 0))", f"AMOUNT < {D60}", (Decimal("1E+5"),), [1, 2, 3, 4, 6]),
    (
        "AMOUNT = typed 1.50 (DECIMAL(3, 2), trailing zero)",
        "AMOUNT = CAST(? AS DECIMAL(3, 2))",
        (Decimal("1.50"),),
        [],
    ),
    ("SMALL IN (untyped 1, typed 100000)", f"SMALL IN (?, {D60})", (1, 100000), [1]),
    (
        "SMALL NOT IN (untyped 1, typed 100000)",
        f"SMALL NOT IN (?, {D60})",
        (1, 100000),
        [2, 3, 4, 6],
    ),
    (
        "SMALL BETWEEN untyped 0 AND typed 100000",
        f"SMALL BETWEEN ? AND {D60}",
        (0, 100000),
        [1, 2, 4, 6],
    ),
    (
        "SMALL BETWEEN typed -100000 AND untyped 0",
        f"SMALL BETWEEN {D60} AND ?",
        (-100000, 0),
        [3, 4],
    ),
    (
        "SMALL = typed 10**20 (DECIMAL(21, 0), beyond BIGINT, int param)",
        "SMALL = CAST(? AS DECIMAL(21, 0))",
        (10**20,),
        None,  # pyodbc cannot bind an int beyond 64 bits (OverflowError): send a Decimal
    ),
    (
        "SMALL < typed 10**20 (DECIMAL(21, 0), Decimal param)",
        "SMALL < CAST(? AS DECIMAL(21, 0))",
        (Decimal(10**20),),
        [1, 2, 3, 4, 6],
    ),
    ("control: SMALL IN (untyped 1, untyped 100000)", "SMALL IN (?, ?)", (1, 100000), None),
    ("control: AMOUNT = untyped 1.005", "AMOUNT = ?", (Decimal("1.005"),), None),
]

# Precision limit: select a value through a typed marker (SYSDUMMY1).
LIMITS: list[tuple[str, str, tuple]] = [
    (
        "DECIMAL(63, 0) with 10**62",
        "SELECT CAST(? AS DECIMAL(63, 0)) FROM SYSIBM.SYSDUMMY1",
        (Decimal(10**62),),
    ),
    (
        "DECIMAL(63, 62) with 0.1234...",
        "SELECT CAST(? AS DECIMAL(63, 62)) FROM SYSIBM.SYSDUMMY1",
        (Decimal("0." + "1234567890" * 6 + "12"),),
    ),
    (
        "DECIMAL(64, 0) with 10**63",
        "SELECT CAST(? AS DECIMAL(64, 0)) FROM SYSIBM.SYSDUMMY1",
        (Decimal(10**63),),
    ),
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _error(exc: Exception) -> str:
    message = str(exc.args[1] if len(exc.args) > 1 else exc)
    code = _SQLCODE.search(message)
    text = re.sub(r"^(\[[^\]]*\]\s*)+", "", message)
    return f"error {code.group(1) if code else exc.args[0]}: {text[:90]}"


def fetch(conn, sql: str, params: tuple) -> Any:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return [row[0] for row in cursor.fetchall()]
    except pyodbc.Error as exc:
        return _error(exc)
    except (OverflowError, TypeError, ValueError) as exc:  # binding, before the driver
        return f"python {type(exc).__name__}: {str(exc)[:80]}"
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    cursor = conn.cursor()
    cursor.execute(f"CREATE TABLE {T} (K INTEGER NOT NULL, SMALL SMALLINT, AMOUNT DECIMAL(5, 2))")
    cursor.executemany(f"INSERT INTO {T} VALUES (?, ?, ?) WITH NC", ROWS)
    cursor.close()
    for label, where, params, expected in CHECKS:
        got = fetch(conn, f"SELECT K FROM {T} WHERE {where} ORDER BY K", params)
        if expected is None:
            verdict = "recorded"
        else:
            verdict = "ok" if got == expected else f"UNEXPECTED (want {expected})"
        results[label] = {"rows": got, "verdict": verdict}
        print(f"  {label:<64} {verdict}: {got}")
    for label, sql, params in LIMITS:
        got = fetch(conn, sql, params)
        results[label] = {"rows": [str(v) for v in got] if isinstance(got, list) else got}
        print(f"  {label:<64} {results[label]['rows']}")
    cursor = conn.cursor()
    cursor.execute(f"DROP TABLE {T}")
    cursor.close()
    return results
