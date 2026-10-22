"""Write probe 13: foreign keys, unique and check constraints, DDL rollback (phase 4, step A).

THIS CHANGES THE IBM i: tables with the prefix DJW13 in the journaled
default library, all dropped at the end (also after a failure). Approved by
the maintainer on 2026-10-21 (phase 4 decision 3) under these conditions:
own prefixed tables, always cleaned up, nothing else read or changed, one
connection, nothing else on PUB400 at the same time (scripts/pub400.sh holds
the PUB400 lock for the whole run). Not part of probes/run.py.

Usage (inside the "tests" container, through scripts/pub400.sh):
    nox -s probe_constraints              # dry run: checks only
    nox -s probe_constraints -- --execute

Questions (docs/phases/phase-4.md, section 4):
1. each kind of foreign key violation (insert or update a child with a
   missing parent, delete or update a referenced parent): SQLSTATE and
   SQLCODE as the driver reports them (SQL0530 / SQL0531 / SQL0532, #96);
2. whether Db2 for i creates or shares an index for a foreign key
   (indexes_foreign_keys), and Django's own index on the column next to it;
3. two constraints on the same columns: a unique constraint and a unique
   index, two unique constraints, two foreign keys;
4. a CHECK constraint: add, violate, how SYSCHKCST records it, drop;
5. whether DDL under commitment control is rolled back (can_rollback_ddl):
   CREATE TABLE and ADD COLUMN, then ROLLBACK.

Every catalog query is limited to the probe's own tables. DROP COLUMN on a
constrained column needs a CPA32B2 reply list entry and is not part of it.
"""

from __future__ import annotations

import argparse
import contextlib
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

PARENT, CHILD, ROLLED = "DJW13P", "DJW13C", "DJW13R"
OWN_TABLES = (PARENT, CHILD, ROLLED)
PROBE_OBJECTS = (
    "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X WHERE OBJNAME LIKE 'DJW13%'"
)
INDEXES = (
    "SELECT INDEX_NAME, TABLE_NAME, IS_UNIQUE FROM QSYS2.SYSINDEXES "
    "WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN ({names}) ORDER BY INDEX_NAME"
)


def checks(conn, library: str) -> None:
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
    existing = run_query(
        conn,
        f"{library}: probe tables that exist already",
        PROBE_OBJECTS,
        (library,),
    )
    for result in (journal, existing):
        print_query(result)
    if not journal["ok"] or not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; nothing was changed")
    if existing["rows"]:
        raise ProbeError("check", f"DJW13 tables exist in {library}; nothing was changed")


def _own(conn, label: str, sql: str, library: str) -> dict[str, Any]:
    """A catalog query limited to the probe's own tables (TABLE_SCHEMA, TABLE_NAME IN ...)."""
    marks = ", ".join("?" for _ in OWN_TABLES)
    result = run_query(conn, label, sql.format(names=marks), (library, *OWN_TABLES))
    print_query(result)
    return result


def run(conn, library: str) -> dict[str, Any]:
    parent, child, rolled = (f"{library}.{name}" for name in OWN_TABLES)
    steps: list[dict[str, Any]] = []
    catalog: dict[str, Any] = {}

    def stmt(label: str, sql: str) -> dict[str, Any]:
        result = run_statement(conn, label, sql)
        steps.append(result)
        return result

    try:
        print("\n======== setup ========")
        key = "ID INTEGER NOT NULL PRIMARY KEY"
        for label, sql in (
            ("create parent", f"CREATE TABLE {parent} ({key}, CODE INTEGER)"),
            ("create child", f"CREATE TABLE {child} ({key}, P_ID INTEGER, A INTEGER)"),
        ):
            if not stmt(label, sql)["ok"]:
                raise ProbeError("refused", f"{label} failed; nothing else was run")
        catalog["indexes before the foreign key"] = _own(
            conn,
            "SYSINDEXES before the foreign key",
            INDEXES,
            library,
        )
        stmt(
            "add the foreign key (Django's form)",
            f"ALTER TABLE {child} ADD CONSTRAINT DJW13FK FOREIGN KEY (P_ID) "
            f"REFERENCES {parent} (ID)",
        )
        stmt("insert parent 1", f"INSERT INTO {parent} VALUES (1, 10)")
        stmt("insert child 1 -> parent 1", f"INSERT INTO {child} VALUES (1, 1, 5)")

        print("\n======== 1. Foreign key violations ========")
        stmt("insert a child with a missing parent", f"INSERT INTO {child} VALUES (2, 99, 5)")
        stmt("update a child to a missing parent", f"UPDATE {child} SET P_ID = 99 WHERE ID = 1")
        stmt("delete a referenced parent", f"DELETE FROM {parent} WHERE ID = 1")
        stmt("update a referenced parent key", f"UPDATE {parent} SET ID = 2 WHERE ID = 1")
        stmt(
            "update a referenced parent, other column",
            f"UPDATE {parent} SET CODE = 11 WHERE ID = 1",
        )

        print("\n======== 2. Indexes for the foreign key ========")
        catalog["indexes after the foreign key"] = _own(
            conn,
            "SYSINDEXES after the foreign key",
            INDEXES,
            library,
        )
        stmt(
            "Django's own index on the column", f"CREATE INDEX {library}.DJW13CI ON {child} (P_ID)"
        )
        catalog["indexes with Django's index"] = _own(
            conn,
            "SYSINDEXES with Django's index",
            INDEXES,
            library,
        )
        catalog["constraints"] = _own(
            conn,
            "SYSCST",
            "SELECT CONSTRAINT_NAME, TABLE_NAME, CONSTRAINT_TYPE FROM QSYS2.SYSCST "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN ({names}) ORDER BY CONSTRAINT_NAME",
            library,
        )
        catalog["foreign key rules"] = _own(
            conn,
            "SYSREFCST",
            "SELECT R.CONSTRAINT_NAME, R.UNIQUE_CONSTRAINT_NAME, R.UPDATE_RULE, R.DELETE_RULE "
            "FROM QSYS2.SYSREFCST R JOIN QSYS2.SYSCST C "
            "ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA "
            "AND C.CONSTRAINT_NAME = R.CONSTRAINT_NAME "
            "WHERE C.TABLE_SCHEMA = ? AND C.TABLE_NAME IN ({names})",
            library,
        )

        print("\n======== 3. Two constraints on the same columns ========")
        stmt("unique constraint on A", f"ALTER TABLE {child} ADD CONSTRAINT DJW13U1 UNIQUE (A)")
        stmt(
            "unique index on A next to it", f"CREATE UNIQUE INDEX {library}.DJW13UI ON {child} (A)"
        )
        stmt(
            "a second unique constraint on A",
            f"ALTER TABLE {child} ADD CONSTRAINT DJW13U2 UNIQUE (A)",
        )
        stmt(
            "a second foreign key on P_ID",
            f"ALTER TABLE {child} ADD CONSTRAINT DJW13FK2 FOREIGN KEY (P_ID) "
            f"REFERENCES {parent} (ID)",
        )
        catalog["constraints after doubles"] = _own(
            conn,
            "SYSCST after the doubles",
            "SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE FROM QSYS2.SYSCST "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN ({names}) ORDER BY CONSTRAINT_NAME",
            library,
        )

        print("\n======== 4. CHECK constraint ========")
        stmt("add check A >= 0", f"ALTER TABLE {child} ADD CONSTRAINT DJW13CK CHECK (A >= 0)")
        stmt("violate the check", f"INSERT INTO {child} VALUES (3, 1, -1)")
        catalog["check clause"] = _own(
            conn,
            "SYSCHKCST",
            "SELECT K.CONSTRAINT_NAME, K.CHECK_CLAUSE FROM QSYS2.SYSCHKCST K "
            "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = K.CONSTRAINT_SCHEMA "
            "AND C.CONSTRAINT_NAME = K.CONSTRAINT_NAME "
            "WHERE C.TABLE_SCHEMA = ? AND C.TABLE_NAME IN ({names})",
            library,
        )
        stmt("drop the check (DROP CONSTRAINT)", f"ALTER TABLE {child} DROP CONSTRAINT DJW13CK")
        stmt("add the check again", f"ALTER TABLE {child} ADD CONSTRAINT DJW13CK CHECK (A >= 0)")
        stmt("drop the check (DROP CHECK)", f"ALTER TABLE {child} DROP CHECK DJW13CK")

        print("\n======== 5. DDL under commitment control ========")
        conn.autocommit = False
        stmt("create a table, autocommit off", f"CREATE TABLE {rolled} (ID INTEGER)")
        stmt("add a column, autocommit off", f"ALTER TABLE {child} ADD COLUMN B INTEGER")
        conn.rollback()
        conn.autocommit = True
        catalog["after ROLLBACK"] = _own(
            conn,
            "tables and the added column after ROLLBACK",
            "SELECT TABLE_NAME, COLUMN_NAME FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN ({names}) "
            "AND (TABLE_NAME = 'DJW13R' OR COLUMN_NAME = 'B')",
            library,
        )
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        for name in (ROLLED, CHILD, PARENT):  # the child before its parent
            stmt(f"drop {name}", f"DROP TABLE {library}.{name}")
        left = run_query(
            conn,
            "probe tables left",
            PROBE_OBJECTS,
            (library,),
        )
        print_query(left)
        if not left["ok"] or left["rows"]:
            print(f"\nWARNING: DJW13 objects may be left in {library}: {left}", file=sys.stderr)

    print("\nSummary")
    for result in steps:
        state = "ok" if result["ok"] else f"{result.get('sqlstate', '')} {result['message'][:100]}"
        print(f"  {result['label'][:60]:<60} {state}")
    return {"steps": steps, "catalog": catalog, "left": left.get("rows")}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the tables")
    args = parser.parse_args(argv)

    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        # DBQ as the backend sets it: the library becomes CURRENT SCHEMA, so the
        # unqualified constraint and index names land next to their tables
        # (without it, ADD CONSTRAINT fails with SQL5051).
        conn = connect(
            settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1", "DBQ": library}, autocommit=True
        )
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('w13_constraints', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
