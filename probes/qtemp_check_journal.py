"""CHECK constraints on a table that is not journaled, in QTEMP (phase 4 item 11).

Writes only to QTEMP (tables that disappear with the job). QTEMP tables
cannot be journaled, so they stand in for a table in a library without a
journal. With the backend's connection attributes (commitment control on,
TRUEAUTOCOMMIT=1), the probe writes CHECK constraints the ways the schema
editor does:

- a column check in CREATE TABLE (``CHECK (A >= 0)``, the positive integer
  fields);
- a named table check in CREATE TABLE (``CONSTRAINT ... CHECK``, a model's
  CheckConstraint);
- ``ALTER TABLE ... ADD CONSTRAINT ... CHECK`` (AddConstraint, AlterField to a
  positive integer field);

each in autocommit mode and in a transaction that is rolled back (a
migration in ``atomic()``), next to a CREATE TABLE without a constraint as
the control. Constraint names are qualified with QTEMP: an unqualified name
goes to the current schema (SQL5051, probe 24).

Findings go to docs/IBMI_NOTES.md and docs/user/IBM-i-Requirements.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PCKJ"
# (label, statements before the case, the statement probed)
CASES: list[tuple[str, list[str], str]] = [
    ("no constraint (control)", [], f"CREATE TABLE {TABLE} (A INTEGER NOT NULL)"),
    ("column check in CREATE TABLE", [], f"CREATE TABLE {TABLE} (A INTEGER CHECK (A >= 0))"),
    (
        "named check in CREATE TABLE",
        [],
        f"CREATE TABLE {TABLE} (A INTEGER, CONSTRAINT QTEMP.PCKJ_C CHECK (A >= 0))",
    ),
    (
        "ALTER TABLE ADD CONSTRAINT CHECK",
        [f"CREATE TABLE {TABLE} (A INTEGER)"],
        f"ALTER TABLE {TABLE} ADD CONSTRAINT QTEMP.PCKJ_C CHECK (A >= 0)",
    ),
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _case(conn, before: list[str], statement: str, *, autocommit: bool) -> dict[str, Any]:
    _execute(conn, f"DROP TABLE {TABLE}")
    conn.autocommit = True
    for sql in before:
        setup = _execute(conn, sql)
        if setup["result"] != "ok":
            raise RuntimeError(f"setup failed: {sql}: {setup}")
    conn.autocommit = autocommit
    try:
        return _execute(conn, statement)
    finally:
        if not autocommit:
            conn.rollback()
        conn.autocommit = True


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"table": TABLE, "connection": BACKEND}
    try:
        for mode, autocommit in (("autocommit", True), ("transaction", False)):
            results[mode] = {}
            for label, before, statement in CASES:
                outcome = _case(conn, before, statement, autocommit=autocommit)
                results[mode][label] = outcome
                print(f"  {mode:<12} {label:<34} {outcome}")
    finally:
        conn.autocommit = True
        _execute(conn, f"DROP TABLE {TABLE}")
    return results
