"""Probe 22: SQLSTATE and SQLCODE of constraint violations (issue #96).

Writes only to QTEMP (tables that disappear with the job). Django relies on
IntegrityError for constraint violations (get_or_create() catches it on a
race, among others). The backend classifies driver errors by SQLSTATE class
("23" -> IntegrityError) and a small SQLCODE table (drivers/base.py); SQL0545
(CHECK) arrived as SQLSTATE HY000 and became DatabaseError. This probe
triggers each violation, with the backend's connection attributes, and
records the SQLSTATE and SQLCODE the driver reports, plus the class the
backend's current error_class() gives them.

QTEMP tables take no constraints at all: PRIMARY KEY, UNIQUE and CHECK fail
with SQL7008 (no journal). Duplicate keys are probed through a UNIQUE INDEX,
NOT NULL needs none; CHECK violations (SQL0545) cannot be probed here (their
SQLSTATE is known from Django's model_fields.test_integerfield, issue #96).

Foreign key violations (SQL0530 / SQL0531 / SQL0532) cannot be probed here:
a referential constraint needs a journal, and QTEMP tables cannot be
journaled (CREATE TABLE ... REFERENCES QTEMP.x fails with SQL7008). The
backend creates no database-level foreign keys yet (supports_foreign_keys is
False), so Django cannot hit them today; they are probed when foreign keys
are enabled.

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True
AUTOCOMMIT = True
BACKEND = {"CMT": "1", "TRUEAUTOCOMMIT": "1", "NAM": "0", "DFT": "5", "TFT": "2"}
_SQLCODE = re.compile(r"\((-?\d+)\)")

# Each step is tried in order; when a step fails, its fallback is tried.
SETUP = [
    (
        "CREATE TABLE QTEMP.P22P (ID INTEGER NOT NULL PRIMARY KEY, CODE VARCHAR(10) UNIQUE)",
        [
            "CREATE TABLE QTEMP.P22P (ID INTEGER NOT NULL, CODE VARCHAR(10))",
            "CREATE UNIQUE INDEX QTEMP.P22P_ID ON QTEMP.P22P (ID)",
            "CREATE UNIQUE INDEX QTEMP.P22P_CODE ON QTEMP.P22P (CODE)",
        ],
    ),
    (
        "CREATE TABLE QTEMP.P22C (ID INTEGER NOT NULL PRIMARY KEY, "
        "PARENT_ID INTEGER, NAME VARCHAR(10) NOT NULL, QTY INTEGER CHECK (QTY >= 0))",
        [
            # QTEMP tables take no constraints (SQL7008), but NOT NULL is no constraint.
            "CREATE TABLE QTEMP.P22C (ID INTEGER NOT NULL, PARENT_ID INTEGER, "
            "NAME VARCHAR(10) NOT NULL, QTY INTEGER)",
        ],
    ),
    ("INSERT INTO QTEMP.P22P VALUES (1, 'a') WITH NC", []),
    ("INSERT INTO QTEMP.P22C VALUES (10, 1, 'x', 0) WITH NC", []),
]
# (label, expected SQLCODE, sql, params)
VIOLATIONS: list[tuple[str, int, str, tuple]] = [
    ("duplicate primary key", -803, "INSERT INTO QTEMP.P22P VALUES (?, ?) WITH NC", (1, "b")),
    ("duplicate unique key", -803, "INSERT INTO QTEMP.P22P VALUES (?, ?) WITH NC", (2, "a")),
    (
        "NOT NULL",
        -407,
        "INSERT INTO QTEMP.P22C VALUES (?, ?, ?, ?) WITH NC",
        (12, 1, None, 0),
    ),
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _backend_class(sqlstate: str, sqlcode: int | None) -> str:
    """The class the backend's current mapping gives (drivers/base.py)."""
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from django_db2_for_i.drivers import base

    return base.error_class(sqlstate, sqlcode).__name__


def _try(conn, sql: str) -> str:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return "ok"
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        return re.sub(r"^(\[[^\]]*\]\s*)+", "", message)[:90]
    finally:
        cursor.close()


def attempt(conn, sql: str, params: tuple) -> dict[str, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return {"result": "no error"}
    except pyodbc.Error as exc:
        sqlstate = str(exc.args[0]) if exc.args else ""
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        match = _SQLCODE.search(message)
        sqlcode = int(match.group(1)) if match else None
        return {
            "sqlstate": sqlstate,
            "sqlcode": sqlcode,
            "pyodbc class": type(exc).__name__,
            "backend class": _backend_class(sqlstate, sqlcode),
            "message": re.sub(r"^(\[[^\]]*\]\s*)+", "", message)[:90],
        }
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    setup = {}
    for sql, fallback in SETUP:
        outcome = _try(conn, sql)
        if outcome != "ok" and fallback:
            outcome += "; fallback: " + ", ".join(_try(conn, step) for step in fallback)
        setup[sql[:60]] = outcome
        print(f"  setup {sql[:60]:<60} {outcome}")
    results["setup"] = setup
    for label, expected_code, sql, params in VIOLATIONS:
        outcome = attempt(conn, sql, params)
        outcome["expected sqlcode"] = expected_code
        results[label] = outcome
        print(f"\n  {label}")
        for key, value in outcome.items():
            print(f"    {key:<18} {value}")
    for table in ("P22C", "P22P"):
        _try(conn, f"DROP TABLE QTEMP.{table}")
    return results
