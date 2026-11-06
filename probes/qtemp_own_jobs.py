"""The user's own active jobs and the locks in the test libraries.

For a run that stops making progress (no CPU, no network): is an earlier job of
the same user still active on the server, waiting for a message (MSGW) or
holding locks on the test library's objects? Read-only: it selects from
``QSYS2.ACTIVE_JOB_INFO`` (this user's jobs only) and ``QSYS2.OBJECT_LOCK_INFO``
(the two ``.env`` libraries). It changes nothing and ends no job. One
connection, one statement per case, no retries.

Usage (inside the "tests" container):
    nox -s probe -- own_jobs
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_later_flags import connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "read-only (catalog services, no changes)"}
    case(
        conn,
        results,
        "own active jobs",
        "SELECT JOB_NAME, JOB_TYPE, JOB_STATUS, FUNCTION_TYPE, FUNCTION, ELAPSED_CPU_TIME, "
        "JOB_ACTIVE_TIME, CLIENT_IP_ADDRESS "
        "FROM TABLE(QSYS2.ACTIVE_JOB_INFO(CURRENT_USER_LIST_FILTER => USER, "
        "DETAILED_INFO => 'ALL')) ORDER BY JOB_ACTIVE_TIME",
    )
    case(
        conn,
        results,
        "own jobs waiting for a message",
        "SELECT J.JOB_NAME, J.JOB_STATUS, M.MESSAGE_ID, M.MESSAGE_TEXT "
        "FROM TABLE(QSYS2.ACTIVE_JOB_INFO(CURRENT_USER_LIST_FILTER => USER)) J, "
        "TABLE(QSYS2.JOBLOG_INFO(J.JOB_NAME)) M "
        "WHERE J.JOB_STATUS = 'MSGW' AND M.MESSAGE_TYPE = 'INQUIRY'",
    )
    case(
        conn,
        results,
        "locks in the test libraries",
        "SELECT OBJECT_SCHEMA, OBJECT_NAME, OBJECT_TYPE, LOCK_STATE, LOCK_STATUS, JOB_NAME "
        "FROM QSYS2.OBJECT_LOCK_INFO WHERE OBJECT_SCHEMA IN (?, ?) ORDER BY JOB_NAME",
        (settings.default_library, settings.other_library),
    )
    return results
