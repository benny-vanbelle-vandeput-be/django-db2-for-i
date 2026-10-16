"""Write probe 01: commitment control on an unjournaled table, and Unicode column lengths.

THIS CHANGES THE IBM i (one temporary table). It is not part of probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_write -- --library <LIB>             # dry run: checks only
    nox -s probe_write -- --library <LIB> --execute   # creates, uses and drops the table

<LIB> must be owned by the current user and must NOT have a QSQJRN journal:
the point is to see how commit mode *CS behaves on an unjournaled table.

Connection: SQL naming (NAM=0), commit mode *CS (CMT=1). Steps:
1. CREATE TABLE <LIB>.DJPROBE (ID INTEGER, NV NVARCHAR(10), V8 VARCHAR(10) CCSID 1208)
   and check that it is not journaled.
2. *CS, autocommit on:  INSERT, then UPDATE.
3. *CS, autocommit off: INSERT, then ROLLBACK.
4. Autocommit on, statement-level WITH NC: INSERT (baseline without commitment control).
5. Unicode: INSERT ... WITH NC of an emoji and of exactly 10 / 11 accented
   characters into NV and V8 separately; read back with LENGTH and
   CHARACTER_LENGTH, and compare the round trip.
6. DROP TABLE (always attempted).
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

from _common import ProbeError, Settings, connect, print_query, run_query, write_result

TABLE = "DJPROBE"
EMOJI = "\U0001f600"
UNICODE_CASES = {
    "accented x10": "é" * 10,
    "accented x11": "é" * 11,
    "emoji x1": EMOJI,
    "emoji x5": EMOJI * 5,
    "emoji x6": EMOJI * 6,
    "emoji x10": EMOJI * 10,
}

_SYSTEM_NAME = re.compile(r"^[A-Z#@$][A-Z0-9#@$_]{0,9}$")


def statement(conn, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
    """Run one statement; record success or the server's error. Never raises."""
    import pyodbc

    result: dict[str, Any] = {"label": label, "sql": sql, "params": list(params)}
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        result.update(ok=True, rowcount=cursor.rowcount)
    except pyodbc.Error as exc:
        args = exc.args
        result.update(
            ok=False,
            sqlstate=str(args[0]) if len(args) > 1 else "",
            message=str(args[1] if len(args) > 1 else exc),
        )
    finally:
        cursor.close()
    status = "ok" if result["ok"] else f"error: {result['sqlstate']} {result['message']}"
    print(f"\n> [{label}] {sql}\n  {status}")
    return result


def checks(conn, library: str) -> None:
    owned = run_query(
        conn,
        f"{library}: owned by current user",
        "SELECT OBJECT_NAME FROM QSYS2.OBJECT_OWNERSHIP "
        "WHERE AUTHORIZATION_NAME = CURRENT USER AND OBJECT_TYPE = '*LIB' AND OBJECT_NAME = ?",
        (library,),
    )
    journals = run_query(
        conn,
        f"{library}: journals",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN')) X",
        (library,),
    )
    table = run_query(
        conn,
        f"{library}.{TABLE}: exists",
        "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
        (library, TABLE),
    )
    for result in (owned, journals, table):
        print_query(result)
    if not all(r["ok"] for r in (owned, journals, table)):
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not owned["rows"]:
        raise ProbeError("check", f"{library} is not owned by the current user")
    if any(row["OBJNAME"] == "QSQJRN" for row in journals["rows"]):
        raise ProbeError("check", f"{library} has a QSQJRN journal; use an unjournaled library")
    if table["rows"]:
        raise ProbeError("check", f"{library}.{TABLE} already exists; nothing was changed")


def run(conn, library: str) -> dict[str, Any]:
    table = f"{library}.{TABLE}"
    steps: list[dict[str, Any]] = []
    unicode: dict[str, Any] = {}
    create = statement(
        conn,
        "create",
        f"CREATE TABLE {table} (ID INTEGER NOT NULL, NV NVARCHAR(10), V8 VARCHAR(10) CCSID 1208)",
    )
    steps.append(create)
    if not create["ok"]:
        raise ProbeError("refused", "CREATE TABLE failed; nothing else was run")
    try:
        journaled = run_query(
            conn,
            f"{table}: journaling",
            "SELECT OBJNAME, JOURNALED FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X",
            (library, TABLE),
        )
        print_query(journaled)
        steps.append(journaled)

        conn.autocommit = True
        steps.append(
            statement(conn, "*CS autocommit insert", f"INSERT INTO {table} (ID) VALUES (1)")
        )
        steps.append(
            statement(conn, "*CS autocommit update", f"UPDATE {table} SET ID = 11 WHERE ID = 1")
        )

        conn.autocommit = False
        steps.append(
            statement(conn, "*CS transaction insert", f"INSERT INTO {table} (ID) VALUES (2)")
        )
        conn.rollback()
        conn.autocommit = True

        steps.append(
            statement(conn, "WITH NC insert", f"INSERT INTO {table} (ID) VALUES (3) WITH NC")
        )

        for number, (label, text) in enumerate(UNICODE_CASES.items()):
            for offset, column in ((100, "NV"), (200, "V8")):
                row_id = offset + number
                result = statement(
                    conn,
                    f"unicode {column}: {label}",
                    f"INSERT INTO {table} (ID, {column}) VALUES (?, ?) WITH NC",
                    (row_id, text),
                )
                steps.append(result)
                unicode[f"{column} {label}"] = {"id": row_id, "inserted": result["ok"]}

        rows = run_query(conn, f"{table}: rows", f"SELECT ID, NV, V8 FROM {table} ORDER BY ID")
        lengths = run_query(
            conn,
            f"{table}: lengths",
            "SELECT ID, LENGTH(NV) AS NV_LENGTH, CHARACTER_LENGTH(NV) AS NV_CHARS, "
            "LENGTH(V8) AS V8_LENGTH, CHARACTER_LENGTH(V8) AS V8_CHARS "
            f"FROM {table} ORDER BY ID",
        )
        for result in (rows, lengths):
            print_query(result)
            steps.append(result)
        if rows["ok"]:
            by_id = {row["ID"]: row for row in rows["rows"]}
            for key, case in unicode.items():
                column, label = key.split(" ", 1)
                stored = by_id.get(case["id"], {}).get(column)
                case["round_trip"] = stored == UNICODE_CASES[label] if case["inserted"] else None
    finally:
        conn.autocommit = True
        drop = statement(conn, "drop", f"DROP TABLE {table}")
        steps.append(drop)
        if not drop["ok"]:
            print(f"\nWARNING: {table} was NOT dropped; remove it manually.", file=sys.stderr)

    print("\nSummary")
    for result in steps:
        if "rowcount" in result or "sqlstate" in result:
            state = "ok" if result["ok"] else f"{result['sqlstate']} {result['message'][:120]}"
            print(f"  {result['label']:<32} {state}")
    for key, case in unicode.items():
        print(f"  round trip {key:<24} {case.get('round_trip')}")
    return {"steps": steps, "unicode": unicode}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library", required=True, help="unjournaled library owned by you")
    parser.add_argument("--execute", action="store_true", help="create, use and drop the table")
    args = parser.parse_args(argv)
    library = args.library.strip().upper()

    conn = None
    try:
        if not _SYSTEM_NAME.match(library):
            raise ProbeError("config", "--library is not a valid system library name", 1)
        settings = Settings.from_env(need_credentials=True)
        conn = connect(settings, {"NAM": "0", "CMT": "1"}, autocommit=True)
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('w01_commitment', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
