"""Which column type changes Db2 for i makes in place, in QTEMP (phase 4, step C item 9).

Writes only to QTEMP (one table at a time, gone with the job). Like probe 24
(qtemp_alter_table) it changes no job attribute and runs only when the job's
inquiry message reply is *RQD, so a statement that sends CPA32B2 is cancelled
(HY008) and changes nothing.

For every ordered pair of the base column types the backend writes
(DatabaseWrapper.data_types, without the identity clause), one empty table
with a column of the first type gets ALTER COLUMN ... SET DATA TYPE <second>.
An empty table shows the type rules alone: SQL0190 ("attributes not
compatible") means Db2 for i cannot convert the type in place; CPA32B2
(HY008) means it can, but asks first because data may be lost (also on an
empty table, probe 24).

The schema editor raises NotSupportedError up front for the SQL0190 pairs
(docs/IBMI_NOTES.md, "Column type changes in place").
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, JOB_LOG, _execute, _inquiry, _rows

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PTCT"
# One column type per family member the backend writes (base.py data_types).
TYPES = [
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "DECIMAL(9, 2)",
    "DOUBLE",
    "BOOLEAN",
    "CHAR(32)",
    "VARCHAR(39)",
    "NVARCHAR(40)",
    "NCLOB",
    "BLOB",
    "DATE",
    "TIME",
    "TIMESTAMP(6)",
]


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _outcome(result: dict[str, Any], job_log: list[str]) -> str:
    if result["result"] == "ok":
        return "ok"
    if result.get("sqlstate") == "HY008" and "CPD32CE" in job_log:
        return "CPA32B2"
    return f"SQL{abs(result.get('sqlcode') or 0):04d}"


def run(settings: Settings, conn) -> dict[str, Any]:
    inquiry = _inquiry()
    cursor = conn.cursor()
    try:
        reply = inquiry.read_reply(cursor)
    finally:
        cursor.close()
    results: dict[str, Any] = {"inquiry message reply": reply}
    if reply != "*RQD":
        print(f"  the job's inquiry message reply is {reply}, not *RQD; nothing was run")
        return results
    matrix: dict[str, dict[str, str]] = {}
    messages: dict[str, str] = {}
    try:
        for old in TYPES:
            matrix[old] = {}
            for new in TYPES:
                if new == old:
                    continue
                _execute(conn, f"DROP TABLE {TABLE}")
                created = _execute(conn, f"CREATE TABLE {TABLE} (C {old})")
                if created["result"] != "ok":
                    raise RuntimeError(f"setup failed for {old}: {created}")
                result = _execute(conn, f"ALTER TABLE {TABLE} ALTER COLUMN C SET DATA TYPE {new}")
                job_log = [row[0] for row in _rows(conn, JOB_LOG)]
                outcome = _outcome(result, job_log)
                matrix[old][new] = outcome
                if outcome.startswith("SQL"):
                    messages.setdefault(outcome, result.get("message", ""))
            print(f"  {old:<14} " + "  ".join(f"{n}:{o}" for n, o in matrix[old].items()))
    finally:
        _execute(conn, f"DROP TABLE {TABLE}")
    results["matrix"] = matrix
    results["messages"] = messages
    return results
