"""Probe: what a test run left in the two .env libraries (phase 4, step C).

Read-only. For the default and the other library it lists the tables and
views (QSYS2.SYSTABLES) and the constraints with the table they belong to
(QSYS2.SYSCST): names and types only, never table contents. Used to find
the object behind an SQL0601 on a constraint name, which Db2 for i keeps
unique per schema, not per table.
"""

from __future__ import annotations

from typing import Any

from _common import Settings, print_query, run_query

NEEDS_CONNECTION = True
# Constraint names looked up in every schema.
NAMES = ("CONSTRAINT",)


def run(settings: Settings, conn) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for library in filter(None, (settings.default_library, settings.other_library)):
        queries = {
            "tables": run_query(
                conn,
                f"{library}: tables and views",
                "SELECT TABLE_NAME, TABLE_TYPE, SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
                "WHERE TABLE_SCHEMA = ? ORDER BY TABLE_NAME",
                (library,),
            ),
            "constraints": run_query(
                conn,
                f"{library}: constraints",
                "SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE, TABLE_NAME FROM QSYS2.SYSCST "
                "WHERE CONSTRAINT_SCHEMA = ? ORDER BY TABLE_NAME, CONSTRAINT_NAME",
                (library,),
            ),
            "objects": run_query(
                conn,
                f"{library}: objects",
                "SELECT OBJNAME, OBJTYPE, OBJATTRIBUTE, OBJCREATED FROM "
                "TABLE(QSYS2.OBJECT_STATISTICS(?, '*ALL')) X ORDER BY OBJNAME",
                (library,),
            ),
        }
        for query in queries.values():
            print_query(query)
        result[library] = queries
    for view in ("SYSCST", "SYSCHKCST", "SYSKEYCST", "SYSCSTCOL", "SYSCSTDEP"):
        query = run_query(
            conn,
            f"QSYS2.{view}: rows of the constraint names given",
            f"SELECT * FROM QSYS2.{view} WHERE CONSTRAINT_NAME IN ({', '.join('?' * len(NAMES))})",
            NAMES,
        )
        print_query(query)
        result[view] = query
    return result
