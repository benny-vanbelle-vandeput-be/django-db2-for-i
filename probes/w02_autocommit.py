"""Write probe 02: is a single statement atomic in autocommit mode?

THIS CHANGES THE IBM i (one temporary table). It is not part of probes/run.py.

Usage (inside the "tests" container), one connection per run:
    nox -s probe_autocommit -- --true-autocommit 0             # dry run: checks only
    nox -s probe_autocommit -- --true-autocommit 0 --execute
    nox -s probe_autocommit -- --true-autocommit 1 --execute

Django assumes that a single statement in autocommit mode is atomic. This
probe runs, on a journaled table in DB2I_DEFAULT_LIBRARY:

1. CREATE TABLE <LIB>.DJAUTOC (ID INTEGER NOT NULL PRIMARY KEY), check journaling.
2. INSERT ... VALUES (1).
3. INSERT ... VALUES (2), (3), (1): the last row violates the primary key.
4. SELECT the remaining rows: rows 2 and 3 present means the failed statement
   was NOT atomic.
5. The commitment definition of the job (QSYS2.DB_TRANSACTION_INFO).
6. DROP TABLE (always attempted).

Connection: SQL naming (NAM=0), commit mode *CS (CMT=1), autocommit on,
TRUEAUTOCOMMIT=<0|1>.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from _common import (
    ProbeError,
    Settings,
    connect,
    print_query,
    run_query,
    run_statement,
    write_result,
)

TABLE = "DJAUTOC"


def checks(conn, library: str) -> None:
    journal = run_query(
        conn,
        f"{library}: QSQJRN journal",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) X",
        (library,),
    )
    table = run_query(
        conn,
        f"{library}.{TABLE}: exists",
        "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
        (library, TABLE),
    )
    for result in (journal, table):
        print_query(result)
    if not journal["ok"] or not table["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; run setup_journal first")
    if table["rows"]:
        raise ProbeError("check", f"{library}.{TABLE} already exists; nothing was changed")


def run(conn, library: str) -> dict[str, Any]:
    table = f"{library}.{TABLE}"
    steps: list[dict[str, Any]] = []
    create = run_statement(
        conn, "create", f"CREATE TABLE {table} (ID INTEGER NOT NULL PRIMARY KEY)"
    )
    steps.append(create)
    if not create["ok"]:
        raise ProbeError("refused", "CREATE TABLE failed; nothing else was run")
    remaining = None
    try:
        journaled = run_query(
            conn,
            f"{table}: journaling",
            "SELECT OBJNAME, JOURNALED, JOURNAL_NAME "
            "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X",
            (library, TABLE),
        )
        print_query(journaled)
        steps.append(journaled)
        steps.append(run_statement(conn, "seed", f"INSERT INTO {table} (ID) VALUES (1)"))
        steps.append(
            run_statement(
                conn, "multi-row with duplicate", f"INSERT INTO {table} (ID) VALUES (2), (3), (1)"
            )
        )
        rows = run_query(conn, f"{table}: rows", f"SELECT ID FROM {table} ORDER BY ID")
        print_query(rows)
        steps.append(rows)
        if rows["ok"]:
            remaining = [row["ID"] for row in rows["rows"]]
        transaction = run_query(
            conn,
            "commitment definition (QSYS2.DB_TRANSACTION_INFO)",
            "SELECT COMMITMENT_DEFINITION, DEFAULT_LOCK_LEVEL, LOCK_SCOPE, "
            "LOGICAL_UNIT_OF_WORK_STATE, NUMBER_COMMITS, NUMBER_ROLLBACKS "
            "FROM QSYS2.DB_TRANSACTION_INFO WHERE JOB_NAME = QSYS2.JOB_NAME",
        )
        print_query(transaction)
        steps.append(transaction)
    finally:
        drop = run_statement(conn, "drop", f"DROP TABLE {table}")
        steps.append(drop)
        if not drop["ok"]:
            print(f"\nWARNING: {table} was NOT dropped; remove it manually.", file=sys.stderr)

    if remaining is None:
        verdict = "unknown (rows could not be read)"
    elif remaining == [1]:
        verdict = "ATOMIC: the failed statement left no rows"
    else:
        verdict = f"NOT ATOMIC: rows left after the failed statement: {remaining}"
    print(f"\nResult: {verdict}")
    return {"steps": steps, "remaining_ids": remaining, "verdict": verdict}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--true-autocommit", choices=["0", "1"], required=True)
    parser.add_argument("--execute", action="store_true", help="create, use and drop the table")
    args = parser.parse_args(argv)

    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        attributes = {"NAM": "0", "CMT": "1", "TRUEAUTOCOMMIT": args.true_autocommit}
        print(f"Connection attributes: {attributes}, autocommit on")
        conn = connect(settings, attributes, autocommit=True)
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        result["connection_attributes"] = attributes
        name = f"w02_autocommit-tac{args.true_autocommit}"
        print(f"\nresult saved to {write_result(name, result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
