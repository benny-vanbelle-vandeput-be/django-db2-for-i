"""Probe 13: statements that fail, and whether the connection stays usable.

Read-only (SYSDUMMY1, a missing table and the PTF views). Found while
verifying goldens: after a failing statement the connection answered every
further statement with SQL0519 ("Prepared statement STMT0002 in use").

Each scenario runs on a fresh connection with the backend's connection
attributes (pooling off, commitment control *CS). Connections are opened one
at a time: the previous one is closed first. A scenario executes a failing
statement, optionally does a recovery step, closes the failed cursor, and
then runs a plain and a parameterized query (in autocommit, or inside a
transaction).

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings, connect

NEEDS_CONNECTION = True
AUTOCOMMIT = True

# The backend's attributes (drivers/pyodbc.py CONNECTION_DEFAULTS, CMT=1).
BACKEND = {"CMT": "1", "TRUEAUTOCOMMIT": "1", "NAM": "0", "DFT": "5", "TFT": "2"}
_SQLCODE = re.compile(r"\((-?\d+)\)")

PTF = "SELECT MAX(PTF_GROUP_LEVEL) FROM QSYS2.GROUP_PTF_INFO"
PTF_PARAM = f"{PTF} WHERE PTF_GROUP_DESCRIPTION LIKE ?"
CAST_ABC = "SELECT CAST('abc' AS INTEGER) FROM SYSIBM.SYSDUMMY1"
MISSING = "SELECT * FROM NOSUCHLIB.NOSUCHTABLE WHERE X = ?"
DIVIDE = "SELECT 1 FROM SYSIBM.SYSDUMMY1 WHERE 1 = CAST(? AS INTEGER) / 0"
NEXT = "SELECT 1 FROM SYSIBM.SYSDUMMY1"
NEXT_PREPARED = "SELECT CAST(? AS INTEGER) FROM SYSIBM.SYSDUMMY1"
DB2 = ("%DB2%",)

# (label, failing sql, params, recovery step, transaction)
SCENARIOS: list[tuple[str, str, tuple, str | None, bool]] = [
    ("no parameter, error at fetch (SQL0443)", PTF, (), None, False),
    ("cast 'abc' to INTEGER", CAST_ABC, (), None, False),
    ("parameter, error at execute (SQL0443)", PTF_PARAM, DB2, None, False),
    ("parameter, missing table (SQL0204)", MISSING, (1,), None, False),
    ("parameter, division by zero in WHERE", DIVIDE, (1,), None, False),
    ("parameter, SQL0443, transaction", PTF_PARAM, DB2, None, True),
    ("parameter, SQL0443, reuse the failed cursor", PTF_PARAM, DB2, "reuse", False),
    ("parameter, SQL0443, rollback before close", PTF_PARAM, DB2, "rollback", False),
    ("parameter, SQL0443, cancel before close", PTF_PARAM, DB2, "cancel", False),
    ("parameter, SQL0443, failed cursor never closed", PTF_PARAM, DB2, "keep", False),
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False  # as the backend (drivers/pyodbc.py)
    return BACKEND


def _error(exc: Exception) -> str:
    message = str(exc.args[1] if len(exc.args) > 1 else exc)
    code = _SQLCODE.search(message)
    text = re.sub(r"^(\[[^\]]*\]\s*)+", "", message)
    return f"{code.group(1) if code else exc.args[0]}: {text[:80]}"


def _try(func) -> str:
    import pyodbc

    try:
        value = func()
        return "ok" if value is None else f"ok {value}"
    except pyodbc.Error as exc:
        return f"error {_error(exc)}"


def _query(conn, prepared: bool) -> str:
    cursor = conn.cursor()

    def run():
        if prepared:
            cursor.execute(NEXT_PREPARED, (1,))
        else:
            cursor.execute(NEXT)
        return cursor.fetchall()

    try:
        return _try(run)
    finally:
        _try(cursor.close)


def scenario(conn, sql: str, params: tuple, recovery: str | None, transaction: bool) -> dict:
    conn.autocommit = not transaction
    result: dict[str, str] = {}
    failed = conn.cursor()

    def execute():
        if params:
            failed.execute(sql, params)
        else:
            failed.execute(sql)

    result["execute"] = _try(execute)
    if result["execute"] == "ok":
        result["fetch"] = _try(failed.fetchall)
    if recovery == "reuse":
        result["reuse failed cursor"] = _try(lambda: failed.execute(NEXT).fetchall())
    elif recovery == "rollback":
        result["rollback"] = _try(conn.rollback)
    elif recovery == "cancel":
        result["cancel"] = _try(failed.cancel)
    if recovery != "keep":
        result["close failed cursor"] = _try(failed.close)
    result["next query"] = _query(conn, prepared=False)
    result["next prepared query"] = _query(conn, prepared=True)
    if transaction:
        result["rollback"] = _try(conn.rollback)
        result["next prepared query after rollback"] = _query(conn, prepared=True)
    result["third query"] = _query(conn, prepared=True)
    return result


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for number, (label, sql, params, recovery, transaction) in enumerate(SCENARIOS):
        if number:  # one connection at a time: close the previous one first
            conn.close()
            conn = connect(settings, connection_attributes(settings), AUTOCOMMIT)
        outcome = scenario(conn, sql, params, recovery, transaction)
        results[label] = outcome
        print(f"\n  {label}")
        for step, value in outcome.items():
            print(f"    {step:<36} {value}")
    conn.close()
    return results
