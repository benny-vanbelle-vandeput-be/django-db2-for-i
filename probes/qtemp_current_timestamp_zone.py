"""Which zone does ``CURRENT TIMESTAMP`` use? (audit F-01, remediation P-1)

Django writes ``Now()`` as ``CURRENT_TIMESTAMP``. The backend stores datetimes
in the connection's time zone (UTC unless the database's ``TIME_ZONE`` is
set), so ``Now()`` is only right when Db2 for i's ``CURRENT TIMESTAMP`` is in
that zone too. This probe records:

- the client's UTC clock just before and after each query;
- ``CURRENT TIMESTAMP``, ``CURRENT TIMEZONE`` and
  ``CURRENT TIMESTAMP - CURRENT TIMEZONE`` from one statement;
- the system values ``QTIMZON`` and ``QUTCOFFSET``;
- the job's time zone columns of ``QSYS2.ACTIVE_JOB_INFO`` for the own job;
- the same values after ``CHGJOB TIMZON(...)`` on the own job (when it is
  refused, the job log's messages say why: ``QSYS2.JOBLOG_INFO('*')``), for a few time
  zone descriptions (a name that does not exist is recorded as an error), and
  after ``CHGJOB TIMZON(*SYS)``, which is always run at the end to put the job
  back.

Changes only its own job's time zone, and puts it back (``*SYS``) before it
ends, also after an error. No tables, no objects, nothing outside its own
job. One connection, one statement per step, no retries.

Usage (inside the "tests" container):
    nox -s probe -- current_timestamp_zone

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

# Time zone descriptions shipped with IBM i (QN = negative offset, QP =
# positive): US Eastern with daylight saving time, Central Europe with
# daylight saving time, and a fixed +05:30 without it.
ZONES = ("QN0500EST3", "QP0100CET", "QP0530IST")

CLOCK = (
    "SELECT CURRENT TIMESTAMP, CURRENT TIMEZONE, "
    "CURRENT TIMESTAMP - CURRENT TIMEZONE FROM SYSIBM.SYSDUMMY1"
)


def _clock(conn) -> dict[str, Any]:
    """The three values of one statement, with the client's UTC clock around
    it and the difference between the derived UTC value and that clock."""
    import pyodbc

    cursor = conn.cursor()
    before = datetime.now(UTC).replace(tzinfo=None)
    try:
        cursor.execute(CLOCK)
        local, zone, utc = cursor.fetchone()
    except pyodbc.Error as exc:
        return {"result": "error", "message": str(exc)[:160]}
    after = datetime.now(UTC).replace(tzinfo=None)
    return {
        "result": "ok",
        "client_utc_before": before.isoformat(),
        "client_utc_after": after.isoformat(),
        "current_timestamp": local.isoformat(),
        "current_timezone": str(zone),
        "current_timestamp_minus_timezone": utc.isoformat(),
        # Within the round trip when CURRENT TIMESTAMP - CURRENT TIMEZONE is UTC.
        "derived_utc_minus_client_before_s": round((utc - before).total_seconds(), 3),
        "current_timestamp_minus_client_before_s": round((local - before).total_seconds(), 3),
        "round_trip_s": round((after - before).total_seconds(), 3),
    }


def _zone_columns(conn, sql: str) -> dict[str, Any]:
    """Only the columns whose name mentions a zone or the UTC offset."""
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        names = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
    except pyodbc.Error as exc:
        return {"result": "error", "message": str(exc)[:160]}
    keep = [i for i, name in enumerate(names) if "ZONE" in name or "UTC" in name]
    return {
        "result": "ok",
        "rows": [{names[i]: str(row[i]) for i in keep} for row in rows],
    }


def _job_log(conn) -> dict[str, Any]:
    """The last messages of the own job's log: why a command was refused."""
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT MESSAGE_ID, MESSAGE_TEXT FROM TABLE(QSYS2.JOBLOG_INFO('*')) "
            "ORDER BY ORDINAL_POSITION DESC FETCH FIRST 6 ROWS ONLY"
        )
        rows = cursor.fetchall()
    except pyodbc.Error as exc:
        return {"result": "error", "message": str(exc)[:160]}
    return {"result": "ok", "messages": [f"{row[0]}: {str(row[1])[:120]}" for row in rows]}


def _snapshot(conn, results, label: str) -> None:
    _step(results, f"{label}: clock", _clock(conn))
    _step(
        results,
        f"{label}: own job",
        _zone_columns(
            conn,
            "SELECT * FROM TABLE(QSYS2.ACTIVE_JOB_INFO("
            "JOB_NAME_FILTER => '*', DETAILED_INFO => 'ALL'))",
        ),
    )


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {
        "scope": "own job only: its time zone is changed and put back (*SYS); no objects"
    }
    _step(
        results,
        "system values",
        _zone_columns(
            conn,
            "SELECT SYSTEM_VALUE_NAME AS ZONE_VALUE_NAME, "
            "CURRENT_CHARACTER_VALUE AS ZONE_VALUE FROM QSYS2.SYSTEM_VALUE_INFO "
            "WHERE SYSTEM_VALUE_NAME IN ('QTIMZON', 'QUTCOFFSET')",
        ),
    )
    _snapshot(conn, results, "as connected")
    try:
        for zone in ZONES:
            changed = _step(
                results,
                f"CHGJOB TIMZON({zone})",
                _execute(conn, f"CALL QSYS2.QCMDEXC('CHGJOB TIMZON({zone})')"),
            )
            if changed["result"] == "ok":
                _snapshot(conn, results, zone)
            else:
                _step(results, f"CHGJOB TIMZON({zone}): job log", _job_log(conn))
    finally:
        _step(
            results,
            "CHGJOB TIMZON(*SYS)",
            _execute(conn, "CALL QSYS2.QCMDEXC('CHGJOB TIMZON(*SYS)')"),
        )
        _snapshot(conn, results, "back to *SYS")
    return results
