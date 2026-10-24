"""The backend's journal check on the configured libraries, read-only (bin/doctor).

Only reads catalog services; creates and changes nothing, also not in QTEMP.
Runs django_db2_for_i.validation.journal_problem, the check behind the system
check django_db2_for_i.W001, for DB2I_DEFAULT_LIBRARY and DB2I_OTHER_LIBRARY
(the NAME and TEST NAME of both aliases in the IBM i test settings). Fails
when new tables in one of them would not be journaled.
"""

from __future__ import annotations

from typing import Any

from _common import ProbeError, Settings

from django_db2_for_i.validation import journal_problem

NEEDS_CONNECTION = True
EXIT_NOT_JOURNALED = 4


def run(settings: Settings, conn) -> dict[str, Any]:
    roles = {"default": settings.default_library, "other": settings.other_library}
    results: dict[str, Any] = {}
    problems = []
    for role, library in roles.items():
        if not library:
            continue
        cursor = conn.cursor()
        try:
            problem = journal_problem(cursor, library.upper())
        finally:
            cursor.close()
        results[role] = {"library": library, "problem": problem}
        print(f"  {role:<8} {problem or 'journaled: new tables are journaled'}")
        if problem:
            problems.append(f"{role}: {problem}")
    if problems:
        raise ProbeError(
            "journal",
            "; ".join(problems) + " (docs/user/IBM-i-Requirements.md)",
            EXIT_NOT_JOURNALED,
        )
    return results
