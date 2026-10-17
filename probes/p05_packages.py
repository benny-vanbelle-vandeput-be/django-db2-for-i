"""Probe 05: SQL packages (*SQLPKG) created for the current user.

Read-only. The IBM i Access ODBC driver creates extended dynamic SQL packages
(object type *SQLPKG, default library QGPL) unless XDYNAMIC=0. This probe lists:
- every *SQLPKG object owned by the current user (QSYS2.OBJECT_OWNERSHIP),
  with size and created / changed / last used timestamps,
- every *SQLPKG object in DB2I_DEFAULT_LIBRARY and DB2I_OTHER_LIBRARY,
  whoever owns it (QSYS2.OBJECT_STATISTICS).

Run it after a test run to confirm that the backend creates no packages.
"""

from __future__ import annotations

from typing import Any

from _common import Settings, print_query, run_query

NEEDS_CONNECTION = True


def run(settings: Settings, conn) -> dict[str, Any]:
    queries = [
        run_query(
            conn,
            "*SQLPKG owned by current user (QSYS2.OBJECT_OWNERSHIP)",
            "SELECT OBJECT_LIBRARY, OBJECT_NAME, OBJECT_TYPE "
            "FROM QSYS2.OBJECT_OWNERSHIP "
            "WHERE AUTHORIZATION_NAME = CURRENT USER AND OBJECT_TYPE = '*SQLPKG'",
        )
    ]
    owned = queries[0]["rows"] if queries[0]["ok"] else []
    for package in owned:
        library, name = package["OBJECT_LIBRARY"], package["OBJECT_NAME"]
        queries.append(
            run_query(
                conn,
                f"{library}/{name}: details",
                "SELECT OBJNAME, OBJSIZE, OBJCREATED, CHANGE_TIMESTAMP, LAST_USED_TIMESTAMP, "
                "DAYS_USED_COUNT FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*SQLPKG', ?)) X",
                (library, name),
            )
        )
    for library in (settings.default_library, settings.other_library):
        if library:
            queries.append(
                run_query(
                    conn,
                    f"{library}: *SQLPKG objects",
                    "SELECT OBJNAME, OBJOWNER, OBJCREATED, OBJTEXT "
                    "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*SQLPKG')) X",
                    (library,),
                )
            )
    for result in queries:
        print_query(result)

    found = len(owned) + sum(
        len(r["rows"]) for r in queries if r["ok"] and r["label"].endswith("*SQLPKG objects")
    )
    complete = all(r["ok"] for r in queries)
    if not complete:
        verdict = "incomplete: a query failed"
    elif found:
        verdict = f"{found} SQL package(s) found"
    else:
        verdict = "no SQL packages found"
    print(f"\nResult: {verdict}")
    return {"queries": queries, "packages_found": found, "complete": complete}
