"""DatabaseCreation: test database setup and teardown.

Phase 1 implements only the "use existing schema" mode, for systems where
the test user cannot create schemas (such as PUB400)::

    "TEST": {"NAME": "<library>", "CREATE_DB": False}

In this mode the backend never runs CREATE or DROP SCHEMA and never opens
the extra ``_nodb_cursor()`` connection Django uses for CREATE/DROP
DATABASE; everything runs on the alias's own connection. Safety rules
(docs/DECISIONS.md):

- The library must exist and have an active QSQJRN journal.
- A library without the marker table ``DJDB2I_TEST_MARKER`` must not contain
  any table or view: otherwise setup refuses, also with ``--noinput``,
  because it may be a production library.
- Setup creates the marker. It records the run and a snapshot of the tables
  that belong to the library and are never dropped (empty when the library
  was empty).
- Only a marked library's tables from earlier runs (anything not in the
  snapshot) may be dropped, after confirmation or with ``--noinput``;
  ``--keepdb`` reuses them.
- Teardown drops everything not in the marker's snapshot, then the marker.
  With ``--keepdb`` nothing is dropped. Because the snapshot lives in the
  library, a crashed run is cleaned up by the next run.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import re
import uuid
from collections.abc import Callable, Iterable, Mapping

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import NotSupportedError
from django.db.backends.base.creation import BaseDatabaseCreation

from .operations import children_first

logger = logging.getLogger("django_db2_for_i")

MARKER_TABLE = "DJDB2I_TEST_MARKER"
# QSYS2.SYSTABLES.TABLE_TYPE -> object kind for DROP (everything else: TABLE).
_DROP_KIND = {"V": "VIEW", "A": "ALIAS"}
_SYSTEM_NAME = re.compile(r"^[A-Z#@$][A-Z0-9#@$_]{0,9}$")
_NOT_FOUND = -204

JOURNAL_HELP = (
    "Create one (see docs/user/IBM-i-Requirements.md):\n"
    "  CRTJRNRCV JRNRCV({lib}/QSQJRN0001)\n"
    "  CRTJRN JRN({lib}/QSQJRN) JRNRCV({lib}/QSQJRN0001) MNGRCV(*SYSTEM) DLTRCV(*YES)"
)


class TestDatabaseRefused(Exception):
    """The test library is not safe to use; nothing was changed."""

    __test__ = False  # not a pytest test class


@dataclasses.dataclass(frozen=True)
class Marker:
    run_id: str
    created_at: dt.datetime | None
    snapshot: frozenset[str]


@dataclasses.dataclass(frozen=True)
class SetupPlan:
    drop: tuple[str, ...]  # tables from earlier runs to drop before migrating
    snapshot: frozenset[str]  # tables that belong to the library


# --- Pure decision logic (offline tested) --------------------------------------------


def plan_setup(
    library: str,
    inventory: Mapping[str, str],
    allowed: set[str],
    marker: Marker | None,
    *,
    keepdb: bool,
    autoclobber: bool,
    confirm: Callable[[list[str]], bool],
) -> SetupPlan:
    """Decide what setup may do with the tables already in ``library``.

    ``inventory`` maps the library's table/view names (uppercase) to their
    TABLE_TYPE; ``allowed`` are the tables of the models under test.
    Raises TestDatabaseRefused when the library is not safe to use.
    """
    objects = set(inventory) - {MARKER_TABLE}
    if marker is None:
        if not objects:
            return SetupPlan((), frozenset())
        foreign = sorted(objects - allowed)
        if foreign:
            raise TestDatabaseRefused(
                f"Test library {library} contains objects that do not belong to the Django "
                f"models under test: {_names(foreign)}. Nothing was changed. Use a library "
                "that holds nothing but test data."
            )
        raise TestDatabaseRefused(
            f"Test library {library} contains tables of the Django models under test "
            f"({_names(sorted(objects))}) but no {MARKER_TABLE} table, so it does not look "
            "like a test library: it may be a production library. Nothing was changed, also "
            "not with --noinput. Use an empty library for tests, or drop these tables yourself "
            "if you are sure they hold no data you need."
        )
    remnants = sorted(objects - marker.snapshot)
    if not remnants or keepdb:
        return SetupPlan((), marker.snapshot)
    if not autoclobber and not confirm(remnants):
        raise TestDatabaseRefused("Tests cancelled; nothing was changed.")
    return SetupPlan(tuple(remnants), marker.snapshot)


def tables_to_drop(inventory: Mapping[str, str], snapshot: Iterable[str]) -> list[str]:
    """Everything in the library except the snapshot and the marker."""
    return sorted(set(inventory) - set(snapshot) - {MARKER_TABLE})


def drop_order(
    names: Iterable[str], inventory: Mapping[str, str], references: set[tuple[str, str]]
) -> list[tuple[str, str]]:
    """``(kind, name)`` pairs: views, then aliases, then tables children first.

    A plain DROP TABLE on Db2 for i also drops dependent views and the
    foreign keys referencing the table (probe ``probe_drop``); this order
    drops each object explicitly instead.
    """
    names = set(names)
    views = sorted(n for n in names if inventory.get(n) == "V")
    aliases = sorted(n for n in names if inventory.get(n) == "A")
    tables = [n for n in children_first(names - set(views) - set(aliases), references)]
    return (
        [("VIEW", n) for n in views]
        + [("ALIAS", n) for n in aliases]
        + [("TABLE", n) for n in tables]
    )


def _names(names: list[str], limit: int = 10) -> str:
    shown = ", ".join(names[:limit])
    return shown if len(names) <= limit else f"{shown}, ... ({len(names)} in total)"


# --- DatabaseCreation -------------------------------------------------------------


class DatabaseCreation(BaseDatabaseCreation):
    def _existing_schema_mode(self) -> bool:
        return self.connection.settings_dict["TEST"].get("CREATE_DB", True) is False

    def _get_test_db_name(self) -> str:
        if not self._existing_schema_mode():
            raise NotSupportedError(
                "Creating test schemas is not implemented yet. Run tests in an existing, "
                "journaled library: DATABASES[...]['TEST'] = "
                "{'NAME': '<library>', 'CREATE_DB': False}."
            )
        name = str(self.connection.settings_dict["TEST"].get("NAME") or "").upper()
        if not _SYSTEM_NAME.match(name):
            raise ImproperlyConfigured(
                "With TEST['CREATE_DB'] = False, TEST['NAME'] must be the system name of an "
                "existing library (1 to 10 characters)."
            )
        return name

    def _create_test_db(self, verbosity, autoclobber, keepdb=False) -> str:
        library = self._get_test_db_name()
        if library == str(self.connection.settings_dict["NAME"] or "").upper():
            message = (
                f"TEST['NAME'] equals NAME ({library}): the tests run in the application's own "
                "library. This is only safe for a library that holds nothing but test data."
            )
            logger.warning(message)
            self.log(f"WARNING: {message}")
        with self.connection.cursor() as cursor:
            self._check_library(cursor, library)
            inventory = self._inventory(cursor, library)
            marker = self._read_marker(cursor, library) if MARKER_TABLE in inventory else None
            plan = plan_setup(
                library,
                inventory,
                self._allowed_tables(),
                marker,
                keepdb=keepdb,
                autoclobber=autoclobber,
                confirm=lambda remnants: self._confirm(library, remnants),
            )
            if plan.drop:
                if verbosity >= 1:
                    self.log(f"Dropping {len(plan.drop)} table(s) left by an earlier test run...")
                self._drop(cursor, library, plan.drop, inventory)
            self._write_marker(cursor, library, plan.snapshot, create=marker is None)
        return library

    def _destroy_test_db(self, test_database_name, verbosity) -> None:
        library = test_database_name.upper()
        with self.connection.cursor() as cursor:
            inventory = self._inventory(cursor, library)
            if MARKER_TABLE not in inventory:
                raise TestDatabaseRefused(
                    f"{library} has no {MARKER_TABLE} table; nothing was dropped. Remove the "
                    "test tables manually."
                )
            marker = self._read_marker(cursor, library)
            names = tables_to_drop(inventory, marker.snapshot)
            if verbosity >= 2:
                self.log(f"Dropping {len(names)} test table(s) from {library}...")
            self._drop(cursor, library, names, inventory)
            cursor.execute(f"DROP TABLE {_qualified(library, MARKER_TABLE)}")

    def _clone_test_db(self, suffix, verbosity, keepdb=False):
        raise NotSupportedError("Cloning test databases is not supported.")

    # --- Catalog and marker -------------------------------------------------------

    def _check_library(self, cursor, library: str) -> None:
        cursor.execute("SELECT 1 FROM QSYS2.SYSSCHEMAS WHERE SYSTEM_SCHEMA_NAME = %s", [library])
        if cursor.fetchone() is None:
            raise TestDatabaseRefused(
                f"Test library {library} does not exist. With TEST['CREATE_DB'] = False the "
                "backend never creates schemas; create the library first."
            )
        cursor.execute(
            "SELECT JOURNAL_STATE FROM QSYS2.JOURNAL_INFO "
            "WHERE JOURNAL_LIBRARY = %s AND JOURNAL_NAME = 'QSQJRN'",
            [library],
        )
        row = cursor.fetchone()
        if row is None:
            raise TestDatabaseRefused(
                f"Test library {library} has no QSQJRN journal; tables in it would not be "
                f"journaled, so data changes fail with SQL7008. {JOURNAL_HELP.format(lib=library)}"
            )
        if str(row[0]).strip() != "*ACTIVE":
            raise TestDatabaseRefused(
                f"The QSQJRN journal in test library {library} is not active "
                f"(state {str(row[0]).strip()})."
            )

    def _inventory(self, cursor, library: str) -> dict[str, str]:
        """User tables and views; system catalog views are not included.

        Db2 for i creates SQL catalog views (SYSCST, SYSKEYCST, ...;
        SYSTEM_TABLE = 'Y') in a library when its first constraint is
        created. They belong to the system and are never dropped.
        """
        cursor.execute(
            "SELECT TABLE_NAME, TABLE_TYPE FROM QSYS2.SYSTABLES "
            "WHERE SYSTEM_TABLE_SCHEMA = %s AND SYSTEM_TABLE = 'N'",
            [library],
        )
        return {name.rstrip(): kind.rstrip() for name, kind in cursor.fetchall()}

    def _references(self, cursor, library: str) -> set[tuple[str, str]]:
        """Foreign keys ``(child, parent)`` among the library's tables."""
        cursor.execute(
            "SELECT C.TABLE_NAME, P.TABLE_NAME "
            "FROM QSYS2.SYSREFCST R "
            "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA "
            "AND C.CONSTRAINT_NAME = R.CONSTRAINT_NAME "
            "JOIN QSYS2.SYSCST P ON P.CONSTRAINT_SCHEMA = R.UNIQUE_CONSTRAINT_SCHEMA "
            "AND P.CONSTRAINT_NAME = R.UNIQUE_CONSTRAINT_NAME "
            "WHERE C.SYSTEM_TABLE_SCHEMA = %s AND P.SYSTEM_TABLE_SCHEMA = %s",
            [library, library],
        )
        return {(child.rstrip(), parent.rstrip()) for child, parent in cursor.fetchall()}

    def _read_marker(self, cursor, library: str) -> Marker:
        cursor.execute(
            f"SELECT RUN_ID, CREATED_AT, TABLE_NAME FROM {_qualified(library, MARKER_TABLE)}"
        )
        run_id, created_at, snapshot = "", None, set()
        for row_run_id, row_created_at, table_name in cursor.fetchall():
            if table_name is None:
                run_id, created_at = row_run_id.rstrip(), row_created_at
            else:
                snapshot.add(table_name.rstrip())
        return Marker(run_id, created_at, frozenset(snapshot))

    def _write_marker(self, cursor, library: str, snapshot: frozenset[str], create: bool) -> None:
        for sql, params in marker_statements(
            library, uuid.uuid4().hex, _utcnow(), snapshot, create=create
        ):
            cursor.execute(sql, params)

    def _drop(self, cursor, library: str, names: Iterable[str], inventory) -> None:
        """Drop ``names``; raise once at the end, listing every failure."""
        failures = []
        for kind, name in drop_order(names, inventory, self._references(cursor, library)):
            try:
                cursor.execute(f"DROP {kind} {_qualified(library, name)}")
            except Exception as exc:  # report all objects that remain
                if getattr(exc.__cause__, "sqlcode", None) == _NOT_FOUND:
                    continue  # already dropped together with another object
                failures.append(f"{name}: {exc}")
            else:
                logger.info("Dropped test %s %s.%s", kind.lower(), library, name)
        if failures:
            raise TestDatabaseRefused(
                f"Could not drop {len(failures)} object(s) in test library {library}: "
                + "; ".join(failures)
            )

    def _allowed_tables(self) -> set[str]:
        """Tables of the models under test, plus Django's own (uppercase)."""
        names = set(self.connection.introspection.django_table_names())
        names.add("django_migrations")
        for cache in getattr(settings, "CACHES", {}).values():
            if cache.get("BACKEND", "").endswith("DatabaseCache") and cache.get("LOCATION"):
                names.add(cache["LOCATION"])
        return {self.connection.ops.quote_name(name)[1:-1] for name in names}

    def _confirm(self, library: str, remnants: list[str]) -> bool:
        try:
            answer = input(
                f"Test library {library} contains {len(remnants)} table(s) from an earlier "
                f"test run: {_names(remnants)}.\nType 'yes' if you would like to drop them, "
                "or 'no' to cancel: "
            )
        except EOFError:
            return False
        return answer.strip().lower() == "yes"


def marker_statements(
    library: str, run_id: str, now: dt.datetime, snapshot: Iterable[str], *, create: bool
) -> list[tuple[str, list]]:
    """SQL (and params) that (create and) rewrite the marker for a new run."""
    table = _qualified(library, MARKER_TABLE)
    statements: list[tuple[str, list]] = []
    if create:
        statements.append(
            (
                f"CREATE TABLE {table} (RUN_ID CHAR(32) NOT NULL, "
                "CREATED_AT TIMESTAMP NOT NULL, TABLE_NAME NVARCHAR(128))",
                [],
            )
        )
    statements.append((f"DELETE FROM {table}", []))
    statements.append((f"INSERT INTO {table} (RUN_ID, CREATED_AT) VALUES (%s, %s)", [run_id, now]))
    statements.extend(
        (
            f"INSERT INTO {table} (RUN_ID, CREATED_AT, TABLE_NAME) VALUES (%s, %s, %s)",
            [run_id, now, name],
        )
        for name in sorted(snapshot)
    )
    return statements


def _qualified(library: str, name: str) -> str:
    def quote(part: str) -> str:
        return '"{}"'.format(part.replace('"', '""'))

    return f"{quote(library)}.{quote(name)}"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)
