"""How do FOR BIT DATA (CCSID 65535) columns look? (audit F-21, remediation P-4)

Tables created outside Django may have ``CHAR`` or ``VARCHAR`` columns with
``FOR BIT DATA`` (CCSID 65535). ``inspectdb`` maps the column type it reads,
and pyodbc returns what the driver describes. This probe records, for a
``CHAR(3) FOR BIT DATA`` and a ``VARCHAR(3) FOR BIT DATA`` column holding
``X'C1C2C3'`` (EBCDIC "ABC"):

- the Python type and value pyodbc returns, and the driver's description;
- the column's ``DATA_TYPE``, ``CCSID`` and length in ``QSYS2.SYSCOLUMNS``
  (QTEMP may not be listed there; then that is the result);
- ``CAST(col AS VARCHAR(3) CCSID 37)``, what the bytes mean as text.

Writes only to QTEMP (one table, gone with the job), without commitment
control (CMT=0). One connection, one statement per step, no retries.

Usage (inside the "tests" container):
    nox -s probe -- ccsid_65535

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PCCSID"


def connection_attributes(settings: Settings) -> dict[str, str]:
    """The backend's attributes without commitment control (QTEMP has no journal)."""
    import pyodbc

    pyodbc.pooling = False
    return {**BACKEND, "CMT": "0"}


def _values(conn) -> dict[str, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT C, V FROM {TABLE}")
        row = cursor.fetchone()
        return {
            "result": "ok",
            "description": [
                {"name": d[0], "type": getattr(d[1], "__name__", str(d[1])), "size": d[3]}
                for d in cursor.description
            ],
            "python": [{"type": type(value).__name__, "repr": repr(value)} for value in row],
        }
    except pyodbc.Error as exc:
        return {"result": "error", "message": str(exc)[:160]}
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table), CMT=0"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(
        results,
        "create",
        _execute(
            conn,
            f"CREATE TABLE {TABLE} (C CHAR(3) FOR BIT DATA, V VARCHAR(3) FOR BIT DATA)",
        ),
    )
    if created["result"] != "ok":
        return results
    _step(results, "insert", _execute(conn, f"INSERT INTO {TABLE} VALUES (X'C1C2C3', X'C1C2C3')"))
    _step(results, "fetch", _values(conn))
    _step(
        results,
        "SYSCOLUMNS",
        _query(
            conn,
            "SELECT COLUMN_NAME, DATA_TYPE, LENGTH, CCSID FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = 'QTEMP' AND TABLE_NAME = 'PCCSID'",
        ),
    )
    _step(
        results,
        "as text (CCSID 37)",
        _query(
            conn,
            f"SELECT CAST(C AS VARCHAR(3) CCSID 37), CAST(V AS VARCHAR(3) CCSID 37) FROM {TABLE}",
        ),
    )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
