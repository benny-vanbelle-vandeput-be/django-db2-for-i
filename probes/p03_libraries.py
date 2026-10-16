"""Probe 03: candidate libraries and whether they are journaled.

Lists the libraries owned by the current user (plus DB2I_DEFAULT_LIBRARY and
DB2I_OTHER_LIBRARY if set). For each library it reports:
- whether it is visible as an SQL schema,
- the QSQJRN journal and journal receivers in it (QSYS2.OBJECT_STATISTICS),
- journal state (QSYS2.JOURNAL_INFO),
- a QDFTJRN data area (automatic journaling of new objects),
- the number of existing tables.

Commitment control requires journaled tables; libraries created with CRTLIB
do not get a QSQJRN journal automatically. Nothing is created here.
"""

from __future__ import annotations

from typing import Any

from _common import Settings, print_query, run_query

NEEDS_CONNECTION = True

OWNED_LIBRARY_QUERIES = [
    (
        "libraries owned by current user (QSYS2.OBJECT_OWNERSHIP)",
        "SELECT * FROM QSYS2.OBJECT_OWNERSHIP "
        "WHERE AUTHORIZATION_NAME = CURRENT USER AND OBJECT_TYPE = '*LIB'",
        ("OBJECT_NAME", "SYSTEM_OBJECT_NAME"),
    ),
    (
        "schemas owned by current user (QSYS2.SYSSCHEMAS)",
        "SELECT SCHEMA_NAME, SYSTEM_SCHEMA_NAME, SCHEMA_OWNER, SCHEMA_TEXT "
        "FROM QSYS2.SYSSCHEMAS WHERE SCHEMA_OWNER = CURRENT USER",
        ("SYSTEM_SCHEMA_NAME",),
    ),
]


def _owned_libraries(conn) -> tuple[list[str], list[dict[str, Any]]]:
    """Try each source in turn until one works."""
    attempts = []
    for label, sql, name_columns in OWNED_LIBRARY_QUERIES:
        result = run_query(conn, label, sql)
        attempts.append(result)
        print_query(result)
        if result["ok"]:
            names = []
            for row in result["rows"]:
                column = next((c for c in name_columns if row.get(c)), None)
                if column:
                    names.append(str(row[column]).upper())
            return names, attempts
    return [], attempts


def _library_details(conn, library: str) -> dict[str, Any]:
    queries = {
        "schema": run_query(
            conn,
            f"{library}: SQL schema",
            "SELECT SCHEMA_NAME, SYSTEM_SCHEMA_NAME, SCHEMA_OWNER, SCHEMA_TEXT "
            "FROM QSYS2.SYSSCHEMAS WHERE SYSTEM_SCHEMA_NAME = ?",
            (library,),
        ),
        "journal_objects": run_query(
            conn,
            f"{library}: journals and receivers",
            "SELECT OBJNAME, OBJTYPE, OBJCREATED, OBJTEXT "
            "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN *JRNRCV')) X",
            (library,),
        ),
        "journal_info": run_query(
            conn,
            f"{library}: journal state",
            "SELECT * FROM QSYS2.JOURNAL_INFO WHERE JOURNAL_LIBRARY = ?",
            (library,),
        ),
        "qdftjrn": run_query(
            conn,
            f"{library}: QDFTJRN data area",
            "SELECT OBJNAME, OBJTYPE "
            "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*DTAARA', 'QDFTJRN')) X",
            (library,),
        ),
        "tables": run_query(
            conn,
            f"{library}: existing tables",
            "SELECT COUNT(*) AS TABLE_COUNT FROM QSYS2.SYSTABLES WHERE SYSTEM_TABLE_SCHEMA = ?",
            (library,),
        ),
    }
    for result in queries.values():
        print_query(result)

    jrn = queries["journal_objects"]
    if jrn["ok"]:
        has_qsqjrn = any(
            row.get("OBJNAME") == "QSQJRN" and row.get("OBJTYPE") == "*JRN" for row in jrn["rows"]
        )
    else:
        has_qsqjrn = None
    return {"has_qsqjrn": has_qsqjrn, "queries": queries}


def run(settings: Settings, conn) -> dict[str, Any]:
    owned, attempts = _owned_libraries(conn)
    configured = [lib for lib in (settings.default_library, settings.other_library) if lib]
    candidates = list(dict.fromkeys(configured + owned))

    details = {lib: _library_details(conn, lib) for lib in candidates}

    print("\nSummary")
    if not candidates:
        print("  no libraries found")
    configured_roles = {"default": settings.default_library, "other": settings.other_library}
    for lib, data in details.items():
        roles = [role for role, name in configured_roles.items() if name == lib]
        role = f" [{', '.join(roles)}]" if roles else ""
        state = {True: "QSQJRN present", False: "NO QSQJRN", None: "journal check unavailable"}
        print(f"  {lib:<10}{role:<18} {state[data['has_qsqjrn']]}")
    return {"owned_attempts": attempts, "configured": configured, "libraries": details}
