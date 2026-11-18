"""How many parameter markers does one statement accept? (audit F-10, remediation P-5)

The backend sets no ``max_query_params``, so Django sends an ``__in`` list of
any length as one statement with one marker per value. This probe records
``SELECT 1 FROM SYSIBM.SYSDUMMY1 WHERE 1 IN (?, ..., ?)`` with 1,000, 2,000
and 4,000 integer markers, in that order, with the time each takes. (A first
run on 2026-11-17 sent 32,766, 32,767 and 32,768 markers: each SQL0901 "SQL
system error" at prepare, at once. They are not sent again: SQL0901 is a
system error on a shared system.) It stops at the first error or after a step that took more than
10 seconds: a first run that bisected from 32,766 down spent over 10 minutes
in one prepare and was stopped, so large counts are not tried again.

Read-only (``SYSIBM.SYSDUMMY1``). One connection, one statement per step, no
retries.

Usage (inside the "tests" container):
    nox -s probe -- in_list_limit

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import time
from typing import Any

from _common import Settings
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

STEPS = (1_000, 2_000, 4_000)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "read-only (SYSIBM.SYSDUMMY1)"}
    for count in STEPS:
        began = time.monotonic()
        outcome = _accepted(conn, count)
        seconds = round(time.monotonic() - began, 2)
        _step(results, f"{count} markers", {**outcome, "seconds": seconds})
        if outcome["result"] != "ok" or seconds > 10:
            break
    return results


def _accepted(conn, count: int) -> dict[str, Any]:
    markers = ", ".join(["?"] * count)
    return _query(
        conn,
        f"SELECT 1 FROM SYSIBM.SYSDUMMY1 WHERE 1 IN ({markers})",
        tuple(range(1, count + 1)),
    )
