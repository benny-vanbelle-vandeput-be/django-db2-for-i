"""Drop the foreign table TEST_TRG from the default library (one table, approved).

THIS CHANGES THE IBM i: it drops one table. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_drop_test_trg              # dry run: checks only
    bin/probe --approved <link> lib_drop_test_trg -- --execute

TEST_TRG is a table that no test run of this project created (it is not on
the created-objects list): a physical file with a primary key on ID, created
2026-11-14 23:59:36 (IBM i time), found by the read-only probe ``leftovers``.
While it is there, creation.py refuses the library for every IBM i run
("objects that do not belong to the Django models under test").

On DB2I_DEFAULT_LIBRARY only. Checks first, changing nothing when one fails:
the table exists there as a table (TABLE_TYPE 'T', a PF), created at that
time; no view, index or foreign key of another table depends on it. Then
``DROP TABLE <library>.TEST_TRG RESTRICT`` (refused if anything depends on
it) and a check that it is gone. Nothing else in the library is touched (the
QSQJRN journal, its receivers and Db2 for i's catalog views stay).
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

TABLE = "TEST_TRG"
CREATED = "2026-11-14 23:59:36"


def checks(conn, library: str) -> dict[str, Any]:
    table = run_query(
        conn,
        f"{library}.{TABLE}: the table",
        "SELECT TABLE_TYPE FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
        (library, TABLE),
    )
    created = run_query(
        conn,
        f"{library}.{TABLE}: the object",
        "SELECT OBJATTRIBUTE AS ATTR, "
        "VARCHAR_FORMAT(OBJCREATED, 'YYYY-MM-DD HH24:MI:SS') AS CREATED "
        "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X",
        (library, TABLE),
    )
    dependents = run_query(
        conn,
        f"{library}.{TABLE}: what depends on it",
        "SELECT 'VIEW' AS KIND, VIEW_SCHEMA AS OWNER, VIEW_NAME AS NAME FROM QSYS2.SYSVIEWDEP "
        "WHERE OBJECT_SCHEMA = ? AND OBJECT_NAME = ? "
        "UNION ALL SELECT 'INDEX', INDEX_SCHEMA, INDEX_NAME FROM QSYS2.SYSINDEXES "
        "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
        "UNION ALL SELECT 'FOREIGN KEY', C.TABLE_SCHEMA, C.TABLE_NAME FROM QSYS2.SYSREFCST R "
        "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA "
        "AND C.CONSTRAINT_NAME = R.CONSTRAINT_NAME "
        "JOIN QSYS2.SYSCST P ON P.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA "
        "AND P.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
        "WHERE P.TABLE_SCHEMA = ? AND P.TABLE_NAME = ?",
        (library, TABLE, library, TABLE, library, TABLE),
    )
    for result in (table, created, dependents):
        print_query(result)
    if not all(result["ok"] for result in (table, created, dependents)):
        raise ProbeError("check", "the checks could not run; nothing was changed")
    if [row["TABLE_TYPE"].strip() for row in table["rows"]] != ["T"]:
        raise ProbeError("check", f"{TABLE} is not one table in {library}; nothing was changed")
    if [(row["ATTR"].strip(), row["CREATED"]) for row in created["rows"]] != [("PF", CREATED)]:
        raise ProbeError("check", f"{TABLE} is not the PF created {CREATED}; nothing was changed")
    if dependents["rows"]:
        raise ProbeError("check", f"objects depend on {TABLE}; nothing was changed")
    return {"table": table, "created": created, "dependents": dependents}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="drop the table")
    args = parser.parse_args(argv)

    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        conn = connect(settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1"}, autocommit=True)
        result: dict[str, Any] = {"checks": checks(conn, library)}
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to drop the table.")
            return 0
        result["drop"] = run_statement(
            conn, f"drop {TABLE}", f"DROP TABLE {library}.{TABLE} RESTRICT"
        )
        result["after"] = run_query(
            conn,
            f"{library}.{TABLE}: after the drop",
            "SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
            (library, TABLE),
        )
        print_query(result["after"])
        print(f"\nresult saved to {write_result('lib_drop_test_trg', result, settings)}")
        if not result["drop"]["ok"]:
            raise ProbeError("drop", f"DROP TABLE {TABLE} failed (see above)")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
