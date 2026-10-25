"""How OVERRIDE_QAQQINI behaves around transactions and repeated calls, and
how Db2 for i measures the values that a narrowing ALTER COLUMN changes.

Writes only to QTEMP (the job's QAQQINI copy and one-row tables, all gone with
the job) and changes only the probe's own job's query options; a final
OVERRIDE_QAQQINI(3) runs in a ``finally``. Like probe qaqqini_inquiry it runs
only when the job's inquiry message reply is *RQD, so a statement that still
sends CPA32B2 is cancelled (HY008) and the job never waits. Libraries outside
QTEMP are not touched or read.

The connection runs under commitment control (autocommit off, isolation *CS
as the backend uses it); rows are written WITH NC (QTEMP tables have no
journal).

Steps:
a. OVERRIDE_QAQQINI(3) without a copy; (1) twice; (3) twice.
b. (1) + (2, SUPPRESS_INQUIRY_MESSAGES, *YES) in a transaction, then
   ROLLBACK: is the copy (and the option) still there, does DROP COLUMN go
   through?
c. (3) in a transaction, then ROLLBACK: is the copy back?
d. Measuring: LENGTH of NVARCHAR and VARCHAR CCSID 1208 values with an emoji
   and an accented letter; CAST to fewer decimals and to an integer
   (truncation or rounding), from DECIMAL and from DOUBLE.

Usage (inside the "tests" container):
    nox -s probe -- qaqqini_lifecycle

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute, _inquiry, _rows

NEEDS_CONNECTION = True
AUTOCOMMIT = False

OPTION = "SUPPRESS_INQUIRY_MESSAGES"
TABLE = "QTEMP.PQLDROP"
OPTION_ROW = "SELECT VARCHAR(QQVAL, 20) FROM QTEMP.QAQQINI WHERE QQPARM = ?"
OBJECT = "SELECT COUNT(*) FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE', 'QAQQINI')) X"
MEASURES = [
    ("NVARCHAR 'abc'", "VALUES LENGTH(CAST(? AS NVARCHAR(10)))", ("abc",)),
    ("NVARCHAR emoji U+1F600", "VALUES LENGTH(CAST(? AS NVARCHAR(10)))", ("\U0001f600",)),
    ("NVARCHAR 'é'", "VALUES LENGTH(CAST(? AS NVARCHAR(10)))", ("é",)),
    ("VARCHAR CCSID 1208 'abc'", "VALUES LENGTH(CAST(? AS VARCHAR(10) CCSID 1208))", ("abc",)),
    (
        "VARCHAR CCSID 1208 emoji U+1F600",
        "VALUES LENGTH(CAST(? AS VARCHAR(10) CCSID 1208))",
        ("\U0001f600",),
    ),
    ("VARCHAR CCSID 1208 'é'", "VALUES LENGTH(CAST(? AS VARCHAR(10) CCSID 1208))", ("é",)),
    ("NCLOB emoji", "VALUES LENGTH(CAST(? AS NCLOB(1K)))", ("a\U0001f600",)),
    ("DECIMAL 1.2355 -> (9, 2)", "VALUES CAST(CAST(1.2355 AS DECIMAL(9, 4)) AS DECIMAL(9, 2))", ()),
    (
        "DECIMAL -1.2355 -> (9, 2)",
        "VALUES CAST(CAST(-1.2355 AS DECIMAL(9, 4)) AS DECIMAL(9, 2))",
        (),
    ),
    ("DOUBLE 0.29 -> DECIMAL(5, 2)", "VALUES CAST(CAST(0.29 AS DOUBLE) AS DECIMAL(5, 2))", ()),
    ("DECIMAL 2.7 -> INTEGER", "VALUES CAST(CAST(2.7 AS DECIMAL(5, 1)) AS INTEGER)", ()),
    ("DOUBLE 2.7 -> INTEGER", "VALUES CAST(CAST(2.7 AS DOUBLE) AS INTEGER)", ()),
    ("DECIMAL 999.99 -> (4, 2)", "VALUES CAST(CAST(999.99 AS DECIMAL(5, 2)) AS DECIMAL(4, 2))", ()),
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _copy(conn) -> dict[str, Any]:
    """Whether QTEMP/QAQQINI exists, and its option row."""
    exists = _rows(conn, OBJECT)
    state: dict[str, Any] = {"copy exists": bool(exists and exists[0][0])}
    if state["copy exists"]:
        state["option"] = _rows(conn, OPTION_ROW, (OPTION,))
    return state


def _drop_column(conn) -> dict[str, Any]:
    _execute(conn, f"DROP TABLE {TABLE}")
    _execute(conn, f"CREATE TABLE {TABLE} (A INTEGER, B INTEGER)")
    _execute(conn, f"INSERT INTO {TABLE} VALUES (1, 2) WITH NC")
    outcome = _execute(conn, f"ALTER TABLE {TABLE} DROP COLUMN B")
    _execute(conn, f"DROP TABLE {TABLE}")
    conn.commit()
    return outcome


def _report(results: dict[str, Any], key: str, value: Any) -> None:
    results[key] = value
    print(f"  {key}: {value}")


def run(settings: Settings, conn) -> dict[str, Any]:
    inquiry = _inquiry()
    cursor = conn.cursor()
    try:
        reply = inquiry.read_reply(cursor)
    finally:
        cursor.close()
    conn.commit()
    results: dict[str, Any] = {"inquiry message reply": reply}
    if reply != "*RQD":
        print(f"  the job's inquiry message reply is {reply}, not *RQD; nothing was run")
        return results
    try:
        print("\n======== a. Repeated and unpaired calls ========")
        _report(
            results,
            "a. (3) without a copy",
            _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')"),
        )
        _report(results, "a. (1) first", _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')"))
        _report(results, "a. (1) again", _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')"))
        _report(results, "a. copy after (1) twice", _copy(conn))
        _report(results, "a. (3) first", _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')"))
        _report(results, "a. (3) again", _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')"))
        _report(results, "a. copy after (3) twice", _copy(conn))
        conn.commit()

        print("\n======== b. (1) + (2) in a transaction, then ROLLBACK ========")
        _report(results, "b. (1)", _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')"))
        _report(
            results,
            "b. (2)",
            _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(2, ?, ?)", (OPTION, "*YES")),
        )
        _report(results, "b. copy before ROLLBACK", _copy(conn))
        conn.rollback()
        _report(results, "b. copy after ROLLBACK", _copy(conn))
        conn.commit()
        _report(results, "b. DROP COLUMN after ROLLBACK", _drop_column(conn))

        print("\n======== c. (3) in a transaction, then ROLLBACK ========")
        _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')")
        _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(2, ?, ?)", (OPTION, "*YES"))
        conn.commit()
        _report(results, "c. copy before", _copy(conn))
        _report(results, "c. (3)", _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')"))
        conn.rollback()
        _report(results, "c. copy after ROLLBACK", _copy(conn))
        conn.commit()
        _report(results, "c. DROP COLUMN after ROLLBACK", _drop_column(conn))
    finally:
        _report(results, "final (3)", _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')"))
        conn.commit()
    _report(results, "final copy", _copy(conn))
    _report(results, "final DROP COLUMN (baseline)", _drop_column(conn))

    print("\n======== d. Measuring ========")
    for label, sql, params in MEASURES:
        _report(results, f"d. {label}", _rows(conn, sql, params))
    conn.commit()
    return results
