"""Shared helpers for the lib_ probes that need two jobs at the same time
(lib_lock_table #162, lib_select_for_update #237, lib_merge_concurrency #238).

Not a probe itself. Two connections at the same time is the limit these probes
keep to (CLAUDE.md: a lock or concurrency test may use at most three, #234).
Each connection is opened once, never retried. Statements of the second job
that may wait run in a thread, so the first job can commit or roll back while
the second one waits.
"""

from __future__ import annotations

import contextlib
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from _common import ProbeError, Settings, connect, print_query, run_query

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import table_registry

OBJECT = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"
WAIT_SECONDS = 2  # CHGPF WAITRCD: how long a blocked row access waits


def sqlcode(message: str) -> str:
    """SQL0913 from the driver message, or the (-913) pyodbc appends."""
    match = re.search(r"\bSQL(\d{4})\b", message) or re.search(r"\((-\d+)\)", message)
    if not match:
        return "?"
    code = match.group(1)
    return f"SQL{code}" if not code.startswith("-") else f"SQL{abs(int(code)):04d}"


def open_job(
    settings: Settings,
    library: str,
    cmt: str = "1",
    trueautocommit: str = "1",
    autocommit: bool = False,
):
    """One job; by default the backend's connection attributes (CMT=1 is *CS,
    TRUEAUTOCOMMIT=1), autocommit off."""
    return connect(
        settings,
        {"CMT": cmt, "TRUEAUTOCOMMIT": trueautocommit, "DBQ": library},
        autocommit=autocommit,
    )


def system_name(conn, library: str, table: str) -> str:
    """The 10-character system name a CL command needs (CPD0074 otherwise, #237)."""
    names = run_query(
        conn,
        f"system name of {table}",
        "SELECT SYSTEM_TABLE_NAME AS N FROM QSYS2.SYSTABLES "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
        (library, table),
    )
    return names["rows"][0]["N"] if names["ok"] and names["rows"] else table


def timed(conn, label: str, sql: str, params: tuple = (), fetch: bool = False) -> dict[str, Any]:
    """Run one statement; record ok or the SQLCODE, the rows (fetch) and the time. Never raises."""
    import pyodbc

    result: dict[str, Any] = {"label": label, "sql": sql, "params": list(params)}
    start = time.monotonic()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        if fetch:
            result["rows"] = [list(row) for row in cursor.fetchall()]
        else:
            result["rowcount"] = cursor.rowcount
        result["ok"] = True
    except pyodbc.Error as exc:
        args = exc.args
        message = str(args[1] if len(args) > 1 else exc)
        result.update(
            ok=False,
            sqlstate=str(args[0]) if len(args) > 1 else "",
            sqlcode=sqlcode(message),
            message=message[:240],
        )
    finally:
        with contextlib.suppress(Exception):
            cursor.close()
    result["ms"] = round((time.monotonic() - start) * 1000)
    shown = "ok" if result["ok"] else f"{result['sqlcode']} ({result['sqlstate']})"
    print(
        f"  [{label}] {shown}, {result['ms']} ms"
        + (f", rows {result['rows']}" if fetch and result["ok"] else "")
    )
    return result


def end(conn, how: str = "rollback") -> str:
    try:
        conn.commit() if how == "commit" else conn.rollback()
    except Exception as exc:  # recorded, the probe goes on
        return f"error {exc!s:.120}"
    return "ok"


def while_waiting(job_b, label: str, sql: str, params: tuple, job_a, how: str, after: float):
    """B runs the statement in a thread; A commits or rolls back `after` seconds later.
    Returns B's result with what A did and when."""
    box: dict[str, Any] = {}
    thread = threading.Thread(
        target=lambda: box.update(timed(job_b, label, sql, params)), daemon=True
    )
    thread.start()
    time.sleep(after)
    a_end = end(job_a, how)
    thread.join(timeout=120)
    box["a"] = {"did": how, "after_seconds": after, "result": a_end}
    if thread.is_alive():
        box.update(ok=False, still_waiting=True)
    return box


def checks(conn, library: str, tables: tuple[str, ...]) -> None:
    """The library is the default one, journaled, without these tables; the registry is set."""
    schema = run_query(conn, "CURRENT SCHEMA", "SELECT CURRENT SCHEMA AS S FROM SYSIBM.SYSDUMMY1")
    print_query(schema)
    if not schema["ok"] or [row.get("S") for row in schema["rows"]] != [library]:
        raise ProbeError("check", "CURRENT SCHEMA is not the default library; nothing was changed")
    journal = run_query(
        conn,
        f"{library}: QSQJRN journal",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) X",
        (library,),
    )
    print_query(journal)
    if not journal["ok"] or not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; nothing was changed")
    for table in tables:
        if exists(conn, library, table):
            raise ProbeError("check", f"{table} exists in {library}; nothing was changed")
    if table_registry.list_path() is None:
        raise ProbeError(
            "check",
            f"{table_registry.ENV} is not set (run through scripts/pub400.sh); nothing was changed",
        )
    end(conn)


def exists(conn, library: str, table: str) -> bool:
    result = run_query(conn, f"{table} exists", OBJECT, (library, table))
    if not result["ok"]:
        raise ProbeError("check", "the catalog could not be read; stopping")
    return bool(result["rows"])


def create(conn, library: str, table: str, body: str, rows: str) -> None:
    """On the cleanup list first, then CREATE, the rows, WAITRCD; committed."""
    sql = f"CREATE TABLE {library}.{table} ({body})"
    entry = table_registry.parse(sql, library)
    assert entry is not None and entry.name == table
    table_registry.record(table_registry.list_path(), entry)
    created = timed(conn, f"create {table}", sql)
    end(conn, "commit")
    short = system_name(conn, library, table) if created["ok"] else table
    for label, statement in (
        # Before the rows: CHGPF needs the file to itself, and the job may keep the
        # file open after an INSERT.
        (
            f"WAITRCD({WAIT_SECONDS}) of {table} ({short})",
            f"CALL QSYS2.QCMDEXC('CHGPF FILE({library}/{short}) WAITRCD({WAIT_SECONDS})')",
        ),
        (f"rows of {table}", f"INSERT INTO {library}.{table} VALUES {rows}"),
    ):
        if not created["ok"]:
            raise ProbeError("refused", f"create {table} failed: {created.get('message', '')}")
        result = timed(conn, label, statement)
        if not result["ok"]:
            # The command's own messages (CPD...) are in this job's log; read-only.
            log = run_query(
                conn,
                "job log",
                "SELECT MESSAGE_ID, MESSAGE_TEXT FROM TABLE(QSYS2.JOBLOG_INFO('*')) X "
                "ORDER BY ORDINAL_POSITION DESC FETCH FIRST 6 ROWS ONLY",
            )
            print_query(log)
            end(conn)
            raise ProbeError(
                "refused",
                f"{label} failed: {result.get('message', '')}; the cleanup drops what exists",
            )
        end(conn, "commit")


def drop(conn, library: str, tables: tuple[str, ...]) -> dict[str, Any]:
    """Drop the tables that exist, in the order given; report any left."""
    end(conn)
    cleanup: dict[str, Any] = {}
    for table in tables:
        with contextlib.suppress(ProbeError):
            if exists(conn, library, table):
                dropped = timed(conn, f"drop {table}", f"DROP TABLE {library}.{table}")
                cleanup[table] = dropped["ok"] or dropped.get("message", "")
                end(conn, "commit")
    left = []
    for table in tables:
        try:
            if exists(conn, library, table):
                left.append(table)
        except ProbeError:
            left.append(f"{table} (unknown)")
    if left:
        print(f"\nWARNING: {left} may be left in {library}; bin/ibmi-cleanup", file=sys.stderr)
    cleanup["left"] = left
    return cleanup


def outcome(result: dict[str, Any]) -> str:
    """One word for the summary: ok (with rows), or the SQLCODE; with the time."""
    if result.get("still_waiting"):
        return "still waiting"
    text = "ok" if result["ok"] else result.get("sqlcode", "?")
    if result.get("rows") is not None:
        text += f" {result['rows']}"
    return f"{text} ({result['ms']} ms)"
