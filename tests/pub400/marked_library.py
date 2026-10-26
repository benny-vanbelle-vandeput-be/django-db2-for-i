"""The test library's marker for one pub400 test module at a time.

``marked_library()`` runs the creation safety gate (journal check, no foreign
objects, leftovers of a crashed marked run dropped, DJDB2I_TEST_MARKER
written) before a module creates its tables, and drops everything the module
created, then the marker, afterwards. A crash in between leaves a marked
library: the tables on the cleanup list are then dropped by
``bin/ibmi-cleanup --yes`` or by the next run's setup.

The marker has exactly one owner per job: the PUB400 lock allows one job at
a time, and within the job a second ``marked_library()`` while one is active
fails instead of sharing (and later dropping) the other module's marker.

``guard()`` (installed on every connection by conftest.py) fails a test that
creates a table, view or alias outside QTEMP while no module owns the marker:
such an object would block every later module and bin/ibmi-cleanup (a run
of #172 left django_migrations behind that way). Only the creation safety
gate itself may (``unmarked_creates_allowed()``): its setup creates the
marker, and the creation tests check how it refuses unmarked tables.
"""

import contextlib

import pytest
from django.db import connection

from django_db2_for_i.creation import MARKER_TABLE
from tests import table_registry
from tests.pub400.connection_guard import replace_if_unusable

_owner: str | None = None
# unmarked_creates_allowed() blocks that are active.
_allowed = 0


def library() -> str:
    return connection.settings_dict["TEST"]["NAME"].upper()


def tables() -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            # System catalog views (SYSCST, ...) belong to the library, not the tests.
            "SELECT TABLE_NAME FROM QSYS2.SYSTABLES "
            "WHERE SYSTEM_TABLE_SCHEMA = %s AND SYSTEM_TABLE = 'N'",
            [library()],
        )
        return {name.rstrip() for (name,) in cursor.fetchall()}


@contextlib.contextmanager
def marked_library(owner: str):
    """Own the marker of an otherwise empty test library while the block runs;
    the library is left without tables, marker included."""
    global _owner
    if _owner is not None:
        pytest.fail(f"the test library's marker is already owned by {_owner}, not {owner}")
    creation = connection.creation
    with unmarked_creates_allowed():  # the setup creates the marker
        creation._create_test_db(verbosity=0, autoclobber=True, keepdb=False)
    _owner = owner
    try:
        leftover = tables() - {MARKER_TABLE}
        if leftover:
            pytest.fail(f"{library()} is not empty after setup: {sorted(leftover)}")
        yield
    finally:
        replace_if_unusable()
        try:
            creation._destroy_test_db(library(), 0)
        finally:
            _owner = None
        remaining = tables()
        assert not remaining, f"tables left in {library()}: {sorted(remaining)}"


@contextlib.contextmanager
def unmarked_creates_allowed():
    """Let the creation safety gate create objects without a marker owner."""
    global _allowed
    _allowed += 1
    try:
        yield
    finally:
        _allowed -= 1


def guard(execute, sql, params, many, context):
    """Execute wrapper: no CREATE TABLE / VIEW / ALIAS outside QTEMP unless a
    module owns the marker."""
    if isinstance(sql, str) and _owner is None and not _allowed:
        default_library = context["connection"].settings_dict["NAME"] or ""
        entry = table_registry.parse(sql, default_library)
        if entry is not None and entry.library != "QTEMP":
            pytest.fail(
                f"{entry.kind} {entry.library}.{entry.name} created outside a marked "
                "library: create tables only inside marked_library() (a module fixture, "
                "see tests/pub400/marked_library.py) or in QTEMP"
            )
    return execute(sql, params, many, context)


def install_guard() -> None:
    """Add guard() to every connection of this backend, current and future."""
    from django.db import connections
    from django.db.backends.signals import connection_created

    def add(sender, connection, **kwargs):
        if connection.vendor == table_registry.VENDOR and guard not in connection.execute_wrappers:
            connection.execute_wrappers.append(guard)

    connection_created.connect(add, weak=False, dispatch_uid="pub400-marked-library-guard")
    for existing in connections.all(initialized_only=True):
        add(None, existing)
