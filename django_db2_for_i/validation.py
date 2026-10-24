"""DatabaseValidation: system checks for Db2 for i.

``check()`` runs with Django's database checks (``migrate``, ``check
--database <alias>``), once per alias they name:

- ``django_db2_for_i.W001``: new tables in a library of the alias (``NAME``,
  and ``TEST["NAME"]``) would not be journaled, so transactions and
  constraints fail with SQL7008 (docs/user/IBM-i-Requirements.md).
- ``django_db2_for_i.W002``: that could not be checked.

Both can be silenced with ``SILENCED_SYSTEM_CHECKS``; with W001 silenced the
check does not query the server at all.

A table created in a library is journaled when the library has a QSQJRN
journal, or when the library itself is journaled (STRJRNLIB, to a journal of
any name) and new objects inherit that. Both are read from catalog services,
read-only (probe library_journal, docs/IBMI_NOTES.md). A library that does not
exist is not reported here. The STRJRNLIB case rests on IBM's documentation
and is not yet tested on IBM i. creation.py still accepts only QSQJRN for the
test library.

Model checks for Db2 for i limits (e.g. identifier length) come in a later
phase.
"""

from __future__ import annotations

from django.conf import settings
from django.core import checks
from django.db import DatabaseError
from django.db.backends.base.validation import BaseDatabaseValidation

from .creation import _SYSTEM_NAME

W001 = "django_db2_for_i.W001"
W002 = "django_db2_for_i.W002"

JOURNAL_HINT = (
    "Create a QSQJRN journal in it, or journal the library with STRJRNLIB "
    "(docs/user/IBM-i-Requirements.md):\n"
    "  CRTJRNRCV JRNRCV({lib}/QSQJRN0001)\n"
    "  CRTJRN JRN({lib}/QSQJRN) JRNRCV({lib}/QSQJRN0001) MNGRCV(*SYSTEM) DLTRCV(*YES)\n"
    "Tables created before that need STRJRNPF. Silence with "
    f"SILENCED_SYSTEM_CHECKS = ['{W001}']."
)


def _journaling_sql(library: str) -> str:
    # LIBRARY_INFO and OBJECT_STATISTICS are services (system APIs): one that
    # failed with SQL0443 on a parameterized statement would leave the
    # connection unusable (drivers/pyodbc.py), so the validated system name
    # is a literal.
    return (
        "SELECT L.JOURNALED, L.INHERIT_JOURNALING, L.JOURNAL_LIBRARY, L.JOURNAL_NAME, "
        "(SELECT COUNT(*) FROM TABLE(QSYS2.OBJECT_STATISTICS("
        f"'{library}', '*JRN', 'QSQJRN')) J) "
        "FROM TABLE(QSYS2.LIBRARY_INFO(LIBRARY_NAME => "
        f"'{library}', IGNORE_ERRORS => 'YES', DETAILED_INFO => 'NO')) L"
    )


def journal_problem(cursor, library: str) -> str | None:
    """Why new tables in ``library`` would not be journaled, or None.

    None also for a library that does not exist. ``cursor`` is any DB-API
    cursor (bin/doctor runs this through probe journal_check); database
    errors propagate.
    """
    if not _SYSTEM_NAME.match(library):
        raise ValueError(f"{library!r} is not the system name of a library")
    cursor.execute(_journaling_sql(library))
    row = cursor.fetchone()
    if row is None:
        return None
    journaled, inherit, journal_library, journal_name, qsqjrn = (
        value.strip() if isinstance(value, str) else value for value in row
    )
    if qsqjrn or (journaled == "YES" and inherit == "YES"):
        return None
    if journaled == "YES":
        return (
            f"library {library} is journaled to {journal_library}/{journal_name}, but new "
            "objects do not inherit journaling (STRJRNLIB INHRULES), and it has no QSQJRN "
            "journal"
        )
    return f"library {library} has no QSQJRN journal and is not journaled (STRJRNLIB)"


class DatabaseValidation(BaseDatabaseValidation):
    def check(self, **kwargs):
        issues = super().check(**kwargs)
        if W001 in settings.SILENCED_SYSTEM_CHECKS:
            return issues
        return issues + self._check_journaling()

    def _libraries(self) -> list[tuple[str, str]]:
        """(library, setting) for NAME and TEST["NAME"], without duplicates."""
        settings_dict = self.connection.settings_dict
        alias = self.connection.alias
        names = [
            (settings_dict.get("NAME"), f"DATABASES[{alias!r}]['NAME']"),
            (
                (settings_dict.get("TEST") or {}).get("NAME"),
                f"DATABASES[{alias!r}]['TEST']['NAME']",
            ),
        ]
        libraries: dict[str, str] = {}
        for name, setting in names:
            if name:
                libraries.setdefault(str(name).strip().upper(), setting)
        return list(libraries.items())

    def _check_journaling(self) -> list[checks.CheckMessage]:
        issues: list[checks.CheckMessage] = []
        for library, setting in self._libraries():
            try:
                with self.connection.cursor() as cursor:
                    problem = journal_problem(cursor, library)
            except (DatabaseError, ValueError) as exc:
                issues.append(
                    checks.Warning(
                        f"Could not check whether {setting} ({library}) is journaled: {exc}",
                        hint=f"Silence with SILENCED_SYSTEM_CHECKS = ['{W002}'].",
                        id=W002,
                    )
                )
                continue
            if problem:
                issues.append(
                    checks.Warning(
                        f"{setting}: {problem}. New tables in it are not journaled, so "
                        "transactions and constraints fail with SQL7008.",
                        hint=JOURNAL_HINT.format(lib=library),
                        id=W001,
                    )
                )
        return issues
