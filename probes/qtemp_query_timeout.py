"""Does pyodbc's query timeout work against Db2 for i? (audit F-07, remediation P-5)

The backend has no query timeout option. pyodbc sets one through
``Connection.timeout`` (``SQL_ATTR_QUERY_TIMEOUT`` on each statement). This
probe records, with ``timeout = 1``:

- ``CALL QSYS2.QCMDEXC('DLYJOB DLY(5)')`` (the own job waits 5 seconds): how
  long it takes, and the error it gives, if any;
- ``VALUES 1`` right after it on the same connection, to see whether the
  connection is still usable;
- the same ``DLYJOB`` with ``timeout = 0`` (no timeout), for comparison.

Delays only its own job; no objects. One connection, one statement per step,
no retries.

Usage (inside the "tests" container):
    nox -s probe -- query_timeout

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import time
from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

DELAY = "CALL QSYS2.QCMDEXC('DLYJOB DLY(5)')"


def _timed(conn, sql: str) -> dict[str, Any]:
    start = time.monotonic()
    outcome = _execute(conn, sql)
    return {**outcome, "seconds": round(time.monotonic() - start, 2)}


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "own job only (a 5-second DLYJOB); no objects"}
    conn.timeout = 1
    _step(results, "timeout 1: DLYJOB 5 s", _timed(conn, DELAY))
    _step(results, "timeout 1: VALUES 1 afterwards", _query(conn, "VALUES 1"))
    conn.timeout = 0
    _step(results, "timeout 0: DLYJOB 5 s", _timed(conn, DELAY))
    _step(results, "timeout 0: VALUES 1 afterwards", _query(conn, "VALUES 1"))
    return results
