"""Where a library's journaling state can be read, read-only (journal system check).

Only reads catalog services; creates and changes nothing, also not in QTEMP.

A table created in a library is journaled when the library has a QSQJRN
journal, or when the library itself is journaled (STRJRNLIB) and its inherit
rules include new files, to the library's journal, whatever its name. Without
either, constraints (SQL7008, probe check_journal) and transactions fail. The
system check in validation.py and bin/doctor reads that state; this probe
verifies the sources on the configured libraries, a library that does not
exist and QTEMP:

- QSYS2.LIBRARY_INFO: JOURNALED, JOURNAL_LIBRARY, JOURNAL_NAME and
  INHERIT_JOURNALING of the library (DETAILED_INFO => 'NO' skips the size);
- QSYS2.OBJECT_STATISTICS: a QSQJRN journal and a QDFTJRN data area in it;
- the journal of the files that are already there, and what QSYS2.JOURNALED_OBJECTS
  lists for QSQJRN, as a cross-check;
- the single query the check runs, and how long each query takes.
"""

from __future__ import annotations

import time
from typing import Any

from _common import Settings, print_query, run_query

NEEDS_CONNECTION = True

MISSING = "DJDB2INONE"

LIBRARY_INFO = (
    "SELECT JOURNALED, JOURNAL_LIBRARY, JOURNAL_NAME, INHERIT_JOURNALING "
    "FROM TABLE(QSYS2.LIBRARY_INFO(LIBRARY_NAME => ?, DETAILED_INFO => 'NO')) L"
)
LIBRARY_INFO_IGNORE = (
    "SELECT JOURNALED, JOURNAL_LIBRARY, JOURNAL_NAME, INHERIT_JOURNALING "
    "FROM TABLE(QSYS2.LIBRARY_INFO(LIBRARY_NAME => ?, IGNORE_ERRORS => 'YES', "
    "DETAILED_INFO => 'NO')) L"
)
QSQJRN = (
    "SELECT OBJNAME, OBJTYPE, JOURNALED FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) X"
)
QDFTJRN = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*DTAARA', 'QDFTJRN')) X"
TABLE_JOURNALS = (
    "SELECT JOURNALED, JOURNAL_LIBRARY, JOURNAL_NAME, COUNT(*) AS FILES "
    "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X "
    "GROUP BY JOURNALED, JOURNAL_LIBRARY, JOURNAL_NAME"
)
# Which files those are (tables, views, indexes) and their journal.
FILES = (
    "SELECT OBJNAME, OBJATTRIBUTE, SQL_OBJECT_TYPE, JOURNALED, JOURNAL_LIBRARY, JOURNAL_NAME "
    "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X ORDER BY OBJNAME"
)
# What the library's QSQJRN journal itself lists as journaled to it.
JOURNALED_TO_QSQJRN = (
    "SELECT OBJECT_NAME, OBJECT_TYPE, FILE_TYPE "
    "FROM QSYS2.JOURNALED_OBJECTS WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = 'QSQJRN' "
    "ORDER BY OBJECT_NAME"
)
# The query of the system check: one row per existing library.
CHECK = (
    "SELECT L.JOURNALED, L.JOURNAL_LIBRARY, L.JOURNAL_NAME, L.INHERIT_JOURNALING, "
    "(SELECT COUNT(*) FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) J) AS QSQJRN "
    "FROM TABLE(QSYS2.LIBRARY_INFO(LIBRARY_NAME => ?, IGNORE_ERRORS => 'YES', "
    "DETAILED_INFO => 'NO')) L"
)


def _timed(conn, label: str, sql: str, params: tuple) -> dict[str, Any]:
    start = time.perf_counter()
    result = run_query(conn, label, sql, params)
    result["seconds"] = round(time.perf_counter() - start, 3)
    print_query(result)
    return result


def _library(conn, library: str) -> dict[str, Any]:
    return {
        "library_info": _timed(conn, f"{library}: LIBRARY_INFO", LIBRARY_INFO, (library,)),
        "library_info_ignore_errors": _timed(
            conn, f"{library}: LIBRARY_INFO, IGNORE_ERRORS", LIBRARY_INFO_IGNORE, (library,)
        ),
        "qsqjrn": _timed(conn, f"{library}: QSQJRN", QSQJRN, (library,)),
        "qdftjrn": _timed(conn, f"{library}: QDFTJRN", QDFTJRN, (library,)),
        "table_journals": _timed(conn, f"{library}: table journals", TABLE_JOURNALS, (library,)),
        "files": _timed(conn, f"{library}: files", FILES, (library,)),
        "journaled_to_qsqjrn": _timed(
            conn, f"{library}: journaled to QSQJRN", JOURNALED_TO_QSQJRN, (library,)
        ),
        "check": _timed(conn, f"{library}: check query", CHECK, (library, library)),
    }


def run(settings: Settings, conn) -> dict[str, Any]:
    roles = {
        "default": settings.default_library,
        "other": settings.other_library,
        "missing": MISSING,
        "qtemp": "QTEMP",
    }
    results = {role: _library(conn, library) for role, library in roles.items() if library}
    print("\nSummary")
    for role, data in results.items():
        check = data["check"]
        if not check["ok"]:
            summary = f"error {check.get('sqlstate')}: {check.get('message')}"
        else:
            summary = str(check["rows"])
        print(f"  {role:<8} {summary}")
    return results
