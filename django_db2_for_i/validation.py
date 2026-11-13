"""DatabaseValidation: system checks for Db2 for i.

``check()`` runs with Django's database checks (``migrate``, ``check
--database <alias>``), once per alias they name:

- ``django_db2_for_i.W001``: new tables in a library of the alias (``NAME``,
  and ``TEST["NAME"]``) would not be journaled, so transactions and
  constraints fail with SQL7008 (docs/user/IBM-i-Requirements.md).
- ``django_db2_for_i.W002``: that could not be checked.
- ``django_db2_for_i.E001``: a field's ``db_system_name`` is not a valid IBM i
  system name (fields.py).
- ``django_db2_for_i.E002``: two columns of one model would get the same system
  name (an explicit one, or a short column name, which is its own); Db2 for i
  would refuse the table with SQL0612.
- ``django_db2_for_i.E003``: a table's ``Meta.db_system_name`` or an index's
  ``db_system_name`` is not a valid system name, or the SQL name is short enough
  to be its own system name (Db2 for i refuses another one, SQL7029).
- ``django_db2_for_i.E004``: two tables or indexes would get the same system name
  (an explicit one, or a short SQL name, which is its own); both are ``*FILE``
  objects of one library, so Db2 for i refuses the second (SQL0601).
- ``django_db2_for_i.E005``: a model's ``Meta.db_library`` is not a valid library
  name, or the model names a library twice (``db_library`` and a ``db_table`` of
  the form ``'LIB"."TABLE'``; apps.py, #124).

Both can be silenced with ``SILENCED_SYSTEM_CHECKS``; with W001 silenced the
check does not query the server at all.

A table created in a library is journaled when the library has a QSQJRN
journal, or when the library itself is journaled (STRJRNLIB, to a journal of
any name) and new objects inherit that. Both are read from catalog services,
read-only (probe library_journal, docs/IBMI_NOTES.md). A library that does not
exist is not reported here. The STRJRNLIB case rests on IBM's documentation
and is not yet tested on IBM i. creation.py still accepts only QSQJRN for the
test library (#156).

Model checks for Db2 for i limits (e.g. identifier length) come in a later
phase.
"""

from __future__ import annotations

from django.conf import settings
from django.core import checks
from django.db import DatabaseError
from django.db.backends.base.validation import BaseDatabaseValidation

from . import fields as system_names
from .creation import _SYSTEM_NAME
from .schema import split_table

W001 = "django_db2_for_i.W001"
W002 = "django_db2_for_i.W002"
E001 = "django_db2_for_i.E001"
E002 = "django_db2_for_i.E002"
E003 = "django_db2_for_i.E003"
E004 = "django_db2_for_i.E004"
E005 = "django_db2_for_i.E005"

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


def library_journaling(cursor, library: str) -> tuple | None:
    """``(JOURNALED, INHERIT_JOURNALING, JOURNAL_LIBRARY, JOURNAL_NAME, QSQJRN count)``.

    None for a library that does not exist. ``cursor`` is any DB-API cursor;
    database errors propagate.
    """
    if not _SYSTEM_NAME.match(library):
        raise ValueError(f"{library!r} is not the system name of a library")
    cursor.execute(_journaling_sql(library))
    row = cursor.fetchone()
    if row is None:
        return None
    return tuple(value.strip() if isinstance(value, str) else value for value in row)


def journal_problem(cursor, library: str) -> str | None:
    """Why new tables in ``library`` would not be journaled, or None.

    None also for a library that does not exist. ``cursor`` is any DB-API
    cursor (bin/doctor runs this through probe journal_check); database
    errors propagate.
    """
    row = library_journaling(cursor, library)
    return None if row is None else journaling_problem(row, library)


def journaling_problem(row: tuple, library: str) -> str | None:
    """Why new tables would not be journaled, from a ``library_journaling`` row."""
    journaled, inherit, journal_library, journal_name, qsqjrn = row
    if qsqjrn or (journaled == "YES" and inherit == "YES"):
        return None
    if journaled == "YES":
        return (
            f"library {library} is journaled to {journal_library}/{journal_name}, but new "
            "objects do not inherit journaling (STRJRNLIB INHRULES), and it has no QSQJRN "
            "journal"
        )
    return f"library {library} has no QSQJRN journal and is not journaled (STRJRNLIB)"


def _own_system_name(field) -> str:
    """The system name a column gets without help: its name, if that is one."""
    column = (getattr(field, "column", None) or "").upper()
    return column if system_names.SYSTEM_NAME.fullmatch(column) else ""


def check_system_name(field) -> list[checks.CheckMessage]:
    """E001 / E002 for one field (#253)."""
    try:
        explicit = system_names.system_name(field)
    except Exception as exc:  # ImproperlyConfigured from an invalid name
        return [checks.Error(str(exc), obj=field, id=E001)]
    name = explicit or _own_system_name(field)
    if not name or getattr(field, "model", None) is None:
        return []
    for other in field.model._meta.local_concrete_fields:
        if other is field:
            break
        try:
            other_explicit = system_names.system_name(other)
        except Exception:
            continue  # reported on that field
        other_name = other_explicit or _own_system_name(other)
        if other_name == name and (explicit or other_explicit):
            return [
                checks.Error(
                    f"The system name {name!r} of {field.name!r} is the system name of "
                    f"{other.name!r} too; Db2 for i refuses the table (SQL0612).",
                    hint="Give each column of the table its own system name.",
                    obj=field,
                    id=E002,
                )
            ]
    return []


def _object_system_names(model, max_length: int) -> tuple[list, list]:
    """((system name, explicit, description, obj), ...) of the model's table and
    Meta indexes, and the E003 errors met on the way."""
    named, errors = [], []
    library, table = split_table(model._meta.db_table)
    objects = [("table", table, model, system_names.table_system_name)]
    objects += [
        (
            "index",
            index.name,
            model,
            lambda _obj, index=index: system_names.index_system_name(index),
        )
        for index in model._meta.indexes
        if index.name
    ]
    for what, sql_name, obj, read in objects:
        try:
            explicit = read(obj)
        except Exception as exc:  # ImproperlyConfigured from an invalid name
            errors.append(checks.Error(str(exc), obj=obj, id=E003))
            continue
        own = system_names.own_system_name(sql_name)
        if explicit and explicit != sql_name.upper() and len(sql_name) <= max_length:
            errors.append(
                checks.Error(
                    f"The {what} {sql_name!r} is its own IBM i system name; Db2 for i refuses "
                    f"another one ({explicit!r}, SQL7029).",
                    hint="Leave db_system_name out, or give it a name longer than 10 characters.",
                    obj=obj,
                    id=E003,
                )
            )
            continue
        if explicit or own:
            # Tables and indexes of one library share the names (*FILE objects).
            key = (library.upper(), explicit or own)
            named.append((key, bool(explicit), f"{what} {sql_name!r}", obj))
    return named, errors


def check_db_library(model) -> list[checks.CheckMessage]:
    """E005 for one model's ``Meta.db_library`` (#124)."""
    library = getattr(model._meta, "db_library", "") or ""
    if not library:
        return []
    if not system_names.SYSTEM_NAME.fullmatch(library.strip().upper()):
        message = (
            f"db_library {library!r} is not a valid IBM i library name: at most 10 "
            "characters, letters, digits or _, starting with a letter."
        )
    elif split_table(model._meta.db_table)[0].upper() != library.strip().upper():
        message = (
            f"The model names two libraries: db_library {library!r} and db_table "
            f"{model._meta.db_table!r}."
        )
    else:
        return []
    return [
        checks.Error(
            message,
            hint="Give the library once: Meta.db_library, or db_table = 'LIB\".\"TABLE'.",
            obj=model,
            id=E005,
        )
    ]


def check_object_system_names(models, max_length: int = 10) -> list[checks.CheckMessage]:
    """E003 / E004 / E005 for the tables and Meta indexes of ``models`` (#253, #124)."""
    issues, seen = [], {}
    for model in models:
        named, errors = _object_system_names(model, max_length)
        issues += check_db_library(model) + errors
        for (library, name), explicit, description, obj in named:
            other = seen.get((library, name))
            if other is None:
                seen[(library, name)] = (explicit, description)
            elif explicit or other[0]:
                issues.append(
                    checks.Error(
                        f"The system name {name!r} of {description} is the system name of "
                        f"{other[1]} too; Db2 for i refuses the second (SQL0601).",
                        hint="Give each table and index its own system name.",
                        obj=obj,
                        id=E004,
                    )
                )
    return issues


class DatabaseValidation(BaseDatabaseValidation):
    def check_field(self, field, **kwargs):
        return [*super().check_field(field, **kwargs), *check_system_name(field)]

    def check(self, **kwargs):
        issues = super().check(**kwargs) + self._check_object_system_names(kwargs)
        if W001 in settings.SILENCED_SYSTEM_CHECKS:
            return issues
        return issues + self._check_journaling()

    def _check_object_system_names(self, kwargs) -> list[checks.CheckMessage]:
        from django.apps import apps
        from django.db import router

        app_configs = kwargs.get("app_configs")
        models = (
            [model for config in app_configs for model in config.get_models()]
            if app_configs is not None
            else apps.get_models()
        )
        models = [
            model
            for model in models
            if model._meta.managed
            and not model._meta.proxy
            and not model._meta.swapped
            and router.allow_migrate_model(self.connection.alias, model)
        ]
        return check_object_system_names(models)

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
