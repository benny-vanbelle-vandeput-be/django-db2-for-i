"""Which LOB column types Db2 for i refuses in an index (db_index on a
TextField or BinaryField).

Writes only to QTEMP (one table and its indexes, gone with the job). Probe
alter_table showed SQL0350 for an NCLOB column; this one adds BLOB (Django's
BinaryField), CLOB and DBCLOB, with an index on an NVARCHAR column of the
same table as the control.

Usage (inside the "tests" container):
    nox -s probe -- lob_index

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PLOBIX"
COLUMNS = {
    "V": "NVARCHAR(20)",
    "NC": "NCLOB(1M)",
    "BL": "BLOB(1M)",
    "CL": "CLOB(1M)",
    "DB": "DBCLOB(1M)",
}


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    _execute(conn, f"DROP TABLE {TABLE}")
    body = ", ".join(f"{name} {type_}" for name, type_ in COLUMNS.items())
    results["create table"] = _execute(conn, f"CREATE TABLE {TABLE} ({body})")
    print(f"  create table: {results['create table']}")
    for name, type_ in COLUMNS.items():
        outcome = _execute(conn, f"CREATE INDEX QTEMP.PLOBIX_{name} ON {TABLE} ({name})")
        results[f"index on {type_}"] = outcome
        print(f"  index on {type_}: {outcome}")
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
