"""Which statement starts a transaction on Db2 for i, if any (phase 4 item 11a).

Writes nothing, also not in QTEMP: each candidate runs on the backend's
connection attributes (commitment control on, TRUEAUTOCOMMIT=1) with
autocommit off, followed by a ROLLBACK.

With can_rollback_ddl on, ``sqlmigrate`` prints
``connection.ops.start_transaction_sql()`` before a migration's statements
(Django's default ``BEGIN;``). Under commitment control a transaction starts
implicitly with the first statement (probe lib_rollback_ddl: a ROLLBACK
undid DDL without any start statement). The probe records how Db2 for i
answers the start statements other databases use.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute

NEEDS_CONNECTION = True
AUTOCOMMIT = True

CANDIDATES = [
    "BEGIN",
    "BEGIN WORK",
    "BEGIN TRANSACTION",
    "START TRANSACTION",
    "BEGIN ATOMIC END",
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"connection": BACKEND, "statements": {}}
    try:
        conn.autocommit = False
        for statement in CANDIDATES:
            outcome = _execute(conn, statement)
            conn.rollback()
            results["statements"][statement] = outcome
            print(f"  {statement:<20} {outcome}")
    finally:
        conn.rollback()
        conn.autocommit = True
    return results
