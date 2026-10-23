"""Write probe 05: DROP TABLE with foreign keys and views.

THIS CHANGES THE IBM i (temporary tables and a view). Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_drop              # dry run: checks only
    bin/probe --approved <link> lib_drop -- --execute

On DB2I_DEFAULT_LIBRARY (journaled), backend connection settings. For a parent
table DJDRPPAR referenced by DJDRPCHD (foreign key) and a view DJDRPVW on the
child, checks:

1. DROP TABLE parent RESTRICT
2. DROP TABLE parent            (no option)
3. DROP TABLE parent CASCADE    (after re-creating parent and foreign key)
   For 2 and 3: does the child survive, and is its foreign key gone?
4. DROP TABLE child             (no option) while the view depends on it:
   is the view dropped too?

Everything is dropped at the end (always attempted).
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
    run_values,
    write_result,
)

PARENT, CHILD, VIEW = "DJDRPPAR", "DJDRPCHD", "DJDRPVW"
FK = "DJDRPFK"


def checks(conn, library: str) -> None:
    journal = run_query(
        conn,
        f"{library}: QSQJRN journal",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) X",
        (library,),
    )
    existing = run_query(
        conn,
        f"{library}: probe objects exist",
        "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN (?, ?, ?)",
        (library, PARENT, CHILD, VIEW),
    )
    for result in (journal, existing):
        print_query(result)
    if not journal["ok"] or not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; run setup_journal first")
    if existing["rows"]:
        raise ProbeError("check", f"probe objects already exist in {library}; nothing was changed")


def run(conn, library: str) -> dict[str, Any]:
    parent, child, view = (f"{library}.{name}" for name in (PARENT, CHILD, VIEW))
    steps: list[dict[str, Any]] = []

    def stmt(label: str, sql: str) -> dict[str, Any]:
        result = run_statement(conn, label, sql)
        steps.append(result)
        return result

    def state(label: str) -> dict[str, Any]:
        result = run_values(
            conn,
            label,
            "SELECT (SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? "
            "AND TABLE_NAME = ?) AS PARENT_EXISTS, "
            "(SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? "
            "AND TABLE_NAME = ?) AS CHILD_EXISTS, "
            "(SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? "
            "AND TABLE_NAME = ?) AS VIEW_EXISTS, "
            "(SELECT COUNT(*) FROM QSYS2.SYSCST WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
            "AND CONSTRAINT_TYPE = 'FOREIGN KEY') AS CHILD_FKS "
            "FROM SYSIBM.SYSDUMMY1",
            (library, PARENT, library, CHILD, library, VIEW, library, CHILD),
        )
        steps.append(result)
        return result

    create_parent = f"CREATE TABLE {parent} (ID INTEGER NOT NULL PRIMARY KEY)"
    # The constraint name is qualified: unqualified, it would default to the
    # connection's current schema, which must match the table's (SQL5051).
    add_fk = (
        f"ALTER TABLE {child} ADD CONSTRAINT {library}.{FK} FOREIGN KEY (PARENT_ID) "
        f"REFERENCES {parent} (ID)"
    )
    try:
        stmt("create parent", create_parent)
        stmt("create child", f"CREATE TABLE {child} (ID INTEGER NOT NULL, PARENT_ID INTEGER)")
        stmt("add foreign key", add_fk)
        stmt("create view on child", f"CREATE VIEW {view} AS SELECT ID FROM {child}")
        state("state after setup")

        print("\n======== 1. DROP TABLE parent RESTRICT ========")
        stmt("drop parent RESTRICT", f"DROP TABLE {parent} RESTRICT")
        state("state after RESTRICT")

        print("\n======== 2. DROP TABLE parent (no option) ========")
        stmt("drop parent (no option)", f"DROP TABLE {parent}")
        state("state after plain DROP")

        print("\n======== 3. DROP TABLE parent CASCADE ========")
        if state("parent present?")["rows"][0]["PARENT_EXISTS"]["repr"] != "1":
            stmt("re-create parent", create_parent)
            stmt("re-add foreign key", add_fk)
        stmt("drop parent CASCADE", f"DROP TABLE {parent} CASCADE")
        state("state after CASCADE")

        print("\n======== 4. DROP TABLE child with a dependent view ========")
        stmt("drop child (no option)", f"DROP TABLE {child}")
        state("state after dropping child")
    finally:
        for kind, name in (("VIEW", view), ("TABLE", child), ("TABLE", parent)):
            exists = run_query(
                conn,
                f"{name} exists?",
                "SELECT 1 AS X FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
                (library, name.split(".")[1]),
            )
            dropped = exists["ok"] and (
                not exists["rows"] or stmt(f"cleanup {name}", f"DROP {kind} {name} CASCADE")["ok"]
            )
            if not dropped:
                print(f"\nWARNING: {name} was NOT dropped; remove it manually.", file=sys.stderr)

    print("\nSummary")
    for result in steps:
        if "rowcount" in result or "sqlstate" in result:
            text = "ok" if result["ok"] else f"{result['sqlstate']} {result['message'][:110]}"
        else:
            row = result["rows"][0] if result.get("rows") else {}
            text = ", ".join(f"{k}={v['repr']}" for k, v in row.items())
        print(f"  {result['label']:<30} {text}")
    return {"steps": steps}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the objects")
    args = parser.parse_args(argv)

    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        conn = connect(settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1"}, autocommit=True)
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('lib_drop', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
