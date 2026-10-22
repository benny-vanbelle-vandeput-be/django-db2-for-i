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
"""

import contextlib

import pytest
from django.db import connection

from django_db2_for_i.creation import MARKER_TABLE
from tests.pub400.connection_guard import replace_if_unusable

_owner: str | None = None


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
