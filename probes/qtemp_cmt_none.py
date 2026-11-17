"""What do ROLLBACK and savepoints do without commitment control? (audit F-02, remediation P-2)

``isolation_level="*NONE"`` is accepted by the backend and passed as ``CMT=0``,
while ``supports_transactions`` and ``uses_savepoints`` stay True. This probe
records, with autocommit off as inside ``atomic()``:

- ``CMT=0`` (``*NONE``): ``INSERT``, ``ROLLBACK``, then the row count;
  ``SAVEPOINT``, ``INSERT``, ``ROLLBACK TO SAVEPOINT``, the row count;
  ``RELEASE SAVEPOINT``;
- the same with ``CMT=1`` (``*CS``, the backend's default) and ``CMT=2``
  (``*CHG``), for the record: a QTEMP table has no journal, so a write under
  commitment control is expected to be refused (SQL7008).

Writes only to QTEMP (one table per connection, gone with the job). Three
connections, one after another, never two at once. One statement per step,
no retries.

Usage (inside the "tests" container):
    nox -s probe -- cmt_none

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import contextlib
from typing import Any

from _common import Settings, connect
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = False

TABLE = "QTEMP.PCMTN"
LEVELS = (("CMT=0 (*NONE)", "0"), ("CMT=1 (*CS)", "1"), ("CMT=2 (*CHG)", "2"))


def connection_attributes(settings: Settings) -> dict[str, str]:
    """The backend's attributes with ``CMT=0``, the first level of the probe."""
    import pyodbc

    pyodbc.pooling = False
    return {**BACKEND, "CMT": "0"}


def _count(conn) -> dict[str, Any]:
    return _query(conn, f"SELECT COUNT(*) FROM {TABLE}")


def _end(conn, how: str) -> dict[str, Any]:
    import pyodbc

    try:
        conn.commit() if how == "commit" else conn.rollback()
        return {"result": "ok"}
    except pyodbc.Error as exc:
        return {"result": "error", "message": str(exc)[:160]}


def _level(conn, results: dict[str, Any], label: str) -> None:
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(
        results, f"{label}: create", _execute(conn, f"CREATE TABLE {TABLE} (A INTEGER)")
    )
    _step(results, f"{label}: commit the create", _end(conn, "commit"))
    if created["result"] != "ok":
        return
    _step(results, f"{label}: insert 1", _execute(conn, f"INSERT INTO {TABLE} VALUES (1)"))
    _step(results, f"{label}: rollback", _end(conn, "rollback"))
    _step(results, f"{label}: count after rollback", _count(conn))
    _step(
        results,
        f"{label}: savepoint",
        _execute(conn, "SAVEPOINT S1 ON ROLLBACK RETAIN CURSORS"),
    )
    _step(results, f"{label}: insert 2", _execute(conn, f"INSERT INTO {TABLE} VALUES (2)"))
    _step(
        results,
        f"{label}: rollback to savepoint",
        _execute(conn, "ROLLBACK TO SAVEPOINT S1"),
    )
    _step(results, f"{label}: count after rollback to savepoint", _count(conn))
    _step(results, f"{label}: release savepoint", _execute(conn, "RELEASE SAVEPOINT S1"))
    _step(results, f"{label}: final rollback", _end(conn, "rollback"))
    _step(results, f"{label}: final count", _count(conn))
    _execute(conn, f"DROP TABLE {TABLE}")
    _end(conn, "commit")


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {
        "scope": "QTEMP only (one table per connection); three connections, one at a time"
    }
    for index, (label, cmt) in enumerate(LEVELS):
        print(f" -- {label}")
        if index:
            # One connection at a time: close the previous one first.
            with contextlib.suppress(Exception):
                conn.close()
            conn = connect(settings, {**BACKEND, "CMT": cmt}, False)
        try:
            _level(conn, results, label)
        finally:
            if index == len(LEVELS) - 1:
                with contextlib.suppress(Exception):
                    conn.close()
    return results
