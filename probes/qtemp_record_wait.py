"""The record wait (WAITRCD) of a table created with SQL (phase 7, select_for_update).

Django's select_for_update tests expect a second job to wait for a locked row; on
PUB400 it got SQL0913 at once. This reads the "maximum record wait time" of a table
created by CREATE TABLE (and by CREATE TABLE with a primary key's index), through
DSPFD into an outfile in QTEMP, and of the same table after CHGPF WAITRCD(5).

Writes only to QTEMP (a table and the DSPFD outfile, gone with the job); reads
nothing outside it. Without commitment control (CMT=0). One connection, no retries.

Usage (inside the "tests" container):
    nox -s probe -- record_wait

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "PRCDWAIT"
OUTFILE = "PRCDWAITFD"


def _wait(conn, results, key: str) -> None:
    _execute(conn, f"DROP TABLE QTEMP.{OUTFILE}")
    _step(
        results,
        f"{key}: DSPFD",
        _execute(
            conn,
            f"CALL QSYS2.QCMDEXC('DSPFD FILE(QTEMP/{TABLE}) TYPE(*ATR) OUTPUT(*OUTFILE) "
            f"FILEATR(*PF) OUTFILE(QTEMP/{OUTFILE})')",
        ),
    )
    _step(
        results,
        f"{key}: the wait columns",
        _query(
            conn,
            "SELECT COLUMN_NAME, COLUMN_TEXT FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = 'QSYS' AND TABLE_NAME = 'QAFDPHY' "
            "AND (UPPER(COLUMN_TEXT) LIKE '%WAIT%')",
        ),
    )
    _step(results, f"{key}: the outfile", _query(conn, f"SELECT * FROM QTEMP.{OUTFILE}"))


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (a table and an outfile gone with the job)"}
    _execute(conn, f"DROP TABLE QTEMP.{TABLE}")
    created = _step(results, "create", _execute(conn, f"CREATE TABLE QTEMP.{TABLE} (I INTEGER)"))
    if created["result"] != "ok":
        return results
    _wait(conn, results, "after CREATE TABLE")
    _step(
        results,
        "CHGPF WAITRCD(5)",
        _execute(conn, f"CALL QSYS2.QCMDEXC('CHGPF FILE(QTEMP/{TABLE}) WAITRCD(5)')"),
    )
    _wait(conn, results, "after CHGPF WAITRCD(5)")
    for name in (TABLE, OUTFILE):
        _execute(conn, f"DROP TABLE QTEMP.{name}")
    return results
