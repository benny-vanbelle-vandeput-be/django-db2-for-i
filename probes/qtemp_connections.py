"""How many connections at the same time does PUB400 allow this user (#234)?

Read-only: each connection runs ``SELECT 1`` and reads its own job name
(``QSYS2.JOB_NAME``); nothing is created or changed, not even in QTEMP.
Not part of probes/run.py: it opens its own connections.

It departs once, on purpose, from "one connection per run" (docs/DECISIONS.md,
2026-11-11): it opens connections one by one, up to ``--max`` (at most 4),
keeping the earlier ones open. The first refused connection ends the probe at
once, with its SQLSTATE and (scrubbed) message; there are no retries and never
a connection beyond the maximum. At the highest number that worked, every
connection stays open for HOLD_SECONDS, with a ``SELECT 1`` on each every
PING_SECONDS, then all of them are closed in reverse order.

Usage (from the host, through the PUB400 lock):
    bin/probe qtemp_connections [-- --max 2]

Findings go to docs/IBMI_NOTES.md; the result is published with
``bin/probe --publish`` as probes/results/qtemp_connections.json.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from collections.abc import Callable
from typing import Any

from _common import ProbeError, Settings, connect, run_query, write_result

MAX_CONNECTIONS = 4
HOLD_SECONDS = 30
PING_SECONDS = 10

PING = "SELECT 1 AS ONE FROM SYSIBM.SYSDUMMY1"
JOB = "SELECT QSYS2.JOB_NAME AS JOB_NAME FROM SYSIBM.SYSDUMMY1"


def _ping_all(connections: list, label: str) -> list[dict[str, Any]]:
    """One ``SELECT 1`` on every open connection; errors are recorded, never retried."""
    pings = []
    for number, conn in enumerate(connections, start=1):
        result = run_query(conn, f"{label}, connection {number}", PING)
        pings.append({"connection": number, "ok": result["ok"]} | _error(result))
    return pings


def _error(result: dict[str, Any]) -> dict[str, Any]:
    if result["ok"]:
        return {}
    return {"sqlstate": result["sqlstate"], "message": result["message"]}


def run(
    settings: Settings,
    maximum: int = MAX_CONNECTIONS,
    open_connection: Callable[[Settings], Any] = connect,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not 1 <= maximum <= MAX_CONNECTIONS:
        raise ProbeError("config", f"--max must be 1 to {MAX_CONNECTIONS}", 1)
    results: dict[str, Any] = {
        "scope": "read-only (SELECT 1 and the job name; nothing created or changed)",
        "maximum_tried": maximum,
        "steps": [],
    }
    connections: list = []
    try:
        for number in range(1, maximum + 1):
            started = time.monotonic()
            try:
                conn = open_connection(settings)
            except ProbeError as exc:
                if number == 1:
                    raise  # no connection at all: the usual connect failure
                results["refused"] = {
                    "connection": number,
                    "category": exc.category,
                    "message": settings.scrub(str(exc)),
                }
                print(f"\nconnection {number} refused ({exc.category}); stopping, no retry")
                break
            connections.append(conn)
            job = run_query(conn, f"job of connection {number}", JOB)
            step = {
                "connection": number,
                "connect_ms": round((time.monotonic() - started) * 1000),
                "job_name": job["rows"][0]["JOB_NAME"] if job["ok"] else None,
                **_error(job),
                "pings": _ping_all(connections, f"after connection {number}"),
            }
            results["steps"].append(step)
            print(f"\nconnection {number}: job {step['job_name']}, {step['connect_ms']} ms")
        results["connections_open_together"] = len(connections)
        jobs = [step["job_name"] for step in results["steps"] if step["job_name"]]
        results["separate_jobs"] = len(set(jobs)) == len(jobs)
        hold = []
        for second in range(PING_SECONDS, HOLD_SECONDS + 1, PING_SECONDS):
            sleep(PING_SECONDS)
            hold.append({"after_seconds": second, "pings": _ping_all(connections, f"{second} s")})
        results["hold"] = hold
        results["all_pings_ok"] = all(
            ping["ok"]
            for group in [step["pings"] for step in results["steps"]] + [h["pings"] for h in hold]
            for ping in group
        )
    finally:
        for conn in reversed(connections):
            with contextlib.suppress(Exception):
                conn.close()
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="qtemp_connections", description=__doc__.split("\n")[0])
    parser.add_argument("--max", type=int, default=MAX_CONNECTIONS, dest="maximum")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env(need_credentials=True)
        result = run(settings, args.maximum)
        print(f"\nresult saved to {write_result('qtemp_connections', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
