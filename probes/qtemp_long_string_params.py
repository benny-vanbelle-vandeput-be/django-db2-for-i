"""Probe 15: string parameters longer than the column they are compared with.

Writes only to QTEMP (a table that disappears with the job). A Django filter
like ``name__in=["nonexistent"]`` on a ``CharField(max_length=10)`` failed
with CWB0111 ("Input data is too big to fit into field", 30207). This probe
checks, with the backend's connection attributes:

- which comparisons fail (=, IN, <>, LIKE) with an untyped marker;
- whether a typed marker (``CAST(? AS NVARCHAR(n))``) or pyodbc's
  ``setinputsizes`` avoids it;
- that nothing is truncated: a row holding the truncated value
  ``nonexisten`` must never match ``nonexistent``.

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

LONG = "nonexistent"  # 11 characters
TRUNCATED = LONG[:10]
EMOJI = "nonexiste\U0001f600"  # 10 by len(), 11 UTF-16 units

QUERIES = [
    ("= ? (untyped)", "SELECT NAME FROM QTEMP.P15 WHERE NAME = ?", (LONG,)),
    ("IN (?) (untyped)", "SELECT NAME FROM QTEMP.P15 WHERE NAME IN (?)", (LONG,)),
    (
        "NOT IN (?) (untyped)",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME NOT IN (?) ORDER BY NAME",
        (LONG,),
    ),
    ("<> ? (untyped)", "SELECT NAME FROM QTEMP.P15 WHERE NAME <> ? ORDER BY NAME", (LONG,)),
    ("> ? (untyped)", "SELECT NAME FROM QTEMP.P15 WHERE NAME > ? ORDER BY NAME", (LONG,)),
    (
        "> CAST(? AS NVARCHAR(32))",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME > CAST(? AS NVARCHAR(32)) ORDER BY NAME",
        (LONG,),
    ),
    ("LIKE ? (untyped)", "SELECT NAME FROM QTEMP.P15 WHERE NAME LIKE ?", (LONG + "%",)),
    (
        "UPPER(NAME) = UPPER(?) (iexact)",
        "SELECT NAME FROM QTEMP.P15 WHERE UPPER(NAME) = UPPER(?)",
        (LONG,),
    ),
    (
        "= CAST(? AS NVARCHAR(32))",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME = CAST(? AS NVARCHAR(32))",
        (LONG,),
    ),
    (
        "IN (CAST(? AS NVARCHAR(32)))",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME IN (CAST(? AS NVARCHAR(32)))",
        (LONG,),
    ),
    (
        "NOT IN (CAST(? AS NVARCHAR(32)))",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME NOT IN (CAST(? AS NVARCHAR(32))) ORDER BY NAME",
        (LONG,),
    ),
    (
        "= CAST(? AS NVARCHAR(10)) (Value cast to max_length)",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME = CAST(? AS NVARCHAR(10))",
        (LONG,),
    ),
    (
        "(NAME, SMALL) = (CAST(? AS NVARCHAR(10)), ?) (row value)",
        "SELECT NAME FROM QTEMP.P15 WHERE (NAME, SMALL) = (CAST(? AS NVARCHAR(10)), ?)",
        (LONG, 1),
    ),
    (
        "SELECT CAST(? AS NVARCHAR(10)) (selected)",
        "SELECT CAST(? AS NVARCHAR(10)) FROM SYSIBM.SYSDUMMY1",
        (LONG,),
    ),
    (
        "LIKE CAST(? AS NVARCHAR(32))",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME LIKE CAST(? AS NVARCHAR(32))",
        (LONG + "%",),
    ),
    (
        "= ? emoji: 10 by len(), 11 UTF-16 units",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME = ?",
        (EMOJI,),
    ),
    ("LOWER(NAME) = ?", "SELECT NAME FROM QTEMP.P15 WHERE LOWER(NAME) = ?", (LONG,)),
    ("NAME || 'x' = ?", "SELECT NAME FROM QTEMP.P15 WHERE NAME || 'x' = ?", (LONG + "xxxx",)),
    ("SUBSTR(NAME, 1, 3) = ?", "SELECT NAME FROM QTEMP.P15 WHERE SUBSTR(NAME, 1, 3) = ?", (LONG,)),
    (
        "CAST(NAME AS NVARCHAR(16370)) = ?",
        "SELECT NAME FROM QTEMP.P15 WHERE CAST(NAME AS NVARCHAR(16370)) = ?",
        (LONG,),
    ),
    ("SMALLINT = ? with 100000", "SELECT NAME FROM QTEMP.P15 WHERE SMALL = ?", (100000,)),
    ("SMALLINT > ? with 100000", "SELECT NAME FROM QTEMP.P15 WHERE SMALL > ?", (100000,)),
    (
        "DECIMAL(5, 2) = ? 123456.789",
        "SELECT NAME FROM QTEMP.P15 WHERE AMOUNT = ?",
        (Decimal("123456.789"),),
    ),
    ("DECIMAL(5, 2) = ? 1.005", "SELECT NAME FROM QTEMP.P15 WHERE AMOUNT = ?", (Decimal("1.005"),)),
    ("DECIMAL(5, 2) = ? 1.00", "SELECT NAME FROM QTEMP.P15 WHERE AMOUNT = ?", (Decimal("1.00"),)),
    (
        "= ? with a value that fits (control)",
        "SELECT NAME FROM QTEMP.P15 WHERE NAME = ?",
        (TRUNCATED,),
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
    return f"{code.group(1) if code else exc.args[0]}: {text[:90]}"


def attempt(conn, sql: str, params: tuple, sizes=None) -> str:
    import pyodbc

    cursor = conn.cursor()
    try:
        if sizes is not None:
            cursor.setinputsizes(sizes)
        cursor.execute(sql, params)
        rows = [row[0] for row in cursor.fetchall()]
        verdict = (
            "TRUNCATED MATCH"
            if TRUNCATED in rows and params[0] != TRUNCATED and "NOT" not in sql and "<>" not in sql
            else "ok"
        )
        return f"{verdict}: {rows}"
    except pyodbc.Error as exc:
        return f"error {_error(exc)}"
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    import pyodbc

    results: dict[str, Any] = {}
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE QTEMP.P15 (NAME NVARCHAR(10) NOT NULL, SMALL SMALLINT, AMOUNT DECIMAL(5, 2))"
    )
    cursor.execute(
        "INSERT INTO QTEMP.P15 VALUES (?, 1, 1.00), (?, 2, 2.00) WITH NC", (TRUNCATED, "other")
    )
    cursor.close()
    for label, sql, params in QUERIES:
        results[label] = attempt(conn, sql, params)
        print(f"  {label:<44} {results[label]}")
    sized = [(pyodbc.SQL_WVARCHAR, 100, 0)]
    for label, sql, params in QUERIES[:2]:
        key = f"{label} with setinputsizes(WVARCHAR 100)"
        results[key] = attempt(conn, sql, params, sizes=sized)
        print(f"  {key:<44} {results[key]}")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE QTEMP.P15")
    cursor.close()
    return results
