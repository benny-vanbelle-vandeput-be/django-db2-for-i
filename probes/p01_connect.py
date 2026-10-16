"""Probe 01: sign on and run SELECT 1 FROM SYSIBM.SYSDUMMY1.

Also reports driver and server identification from SQLGetInfo, the session's
user, server and job, and (best effort) the server port of this connection,
which shows whether the TLS port was used.
"""

from __future__ import annotations

from typing import Any

from _common import Settings, print_query, run_query

NEEDS_CONNECTION = True


def _getinfo(conn, attribute: str) -> Any:
    import pyodbc

    try:
        return conn.getinfo(getattr(pyodbc, attribute))
    except pyodbc.Error as exc:
        return f"unavailable: {exc.args[0] if exc.args else exc}"


def run(settings: Settings, conn) -> dict[str, Any]:
    info = {
        name: _getinfo(conn, name)
        for name in (
            "SQL_DBMS_NAME",
            "SQL_DBMS_VER",
            "SQL_DRIVER_NAME",
            "SQL_DRIVER_VER",
            "SQL_DRIVER_ODBC_VER",
            "SQL_SERVER_NAME",
        )
    }
    print(f"Connected to {settings.host} (SSL={int(settings.ssl)})")
    for name, value in info.items():
        print(f"  {name:<20} {value}")

    queries = [
        run_query(conn, "SELECT 1", "SELECT 1 AS ONE FROM SYSIBM.SYSDUMMY1"),
        run_query(
            conn,
            "session",
            "SELECT CURRENT USER AS CURRENT_USER, CURRENT SERVER AS CURRENT_SERVER, "
            "CURRENT SCHEMA AS CURRENT_SCHEMA, QSYS2.JOB_NAME AS JOB_NAME "
            "FROM SYSIBM.SYSDUMMY1",
        ),
        run_query(
            conn,
            "this connection (QSYS2.NETSTAT_JOB_INFO)",
            "SELECT * FROM QSYS2.NETSTAT_JOB_INFO WHERE JOB_NAME = QSYS2.JOB_NAME "
            "FETCH FIRST 5 ROWS ONLY",
        ),
    ]
    for result in queries:
        print_query(result)

    select_one = queries[0]
    ok = select_one["ok"] and select_one["rows"] == [{"ONE": 1}]
    print(f"\nSELECT 1 FROM SYSIBM.SYSDUMMY1: {'OK' if ok else 'FAILED'}")
    return {"select_one_ok": ok, "getinfo": info, "queries": queries}
