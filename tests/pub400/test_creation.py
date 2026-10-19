"""Test database creation in the existing default library (writes).

Each test starts from a library without tables (only the QSQJRN journal),
refuses to run otherwise, and leaves the library without tables again. The
default library is both NAME and TEST['NAME'] on PUB400.
"""

import pytest
from django.db import connection

from django_db2_for_i.creation import MARKER_TABLE, TestDatabaseRefused
from tests.testapp.models import Author

MODEL_TABLES = {
    "TESTAPP_AUTHOR",
    "TESTAPP_BOOK",
    "TESTAPP_DEFAULTS",
    "TESTAPP_DOCUMENT",
    "TESTAPP_NODE",
    "TESTAPP_SCHEDULE",
    "TESTAPP_TAG",
}


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


@pytest.fixture(autouse=True)
def empty_library(django_db_blocker):
    with django_db_blocker.unblock():
        existing = tables()
        if existing:
            pytest.fail(f"{library()} is not empty; remove these first: {sorted(existing)}")
        try:
            yield
        finally:
            if MARKER_TABLE in tables():  # a failed test left a marked test library
                connection.creation._destroy_test_db(library(), 0)
            assert tables() == set(), f"tables left in {library()}: {sorted(tables())}"


def test_create_and_destroy(caplog) -> None:
    with caplog.at_level("WARNING", logger="django_db2_for_i"):
        name = connection.creation.create_test_db(verbosity=0, autoclobber=True, keepdb=False)
    assert name == library()
    assert "TEST['NAME'] equals NAME" in caplog.text
    # testapp has no migrations (run_syncdb), so migrate creates no
    # django_migrations table: exactly the model tables and the marker.
    assert tables() == MODEL_TABLES | {MARKER_TABLE}
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT RUN_ID, TABLE_NAME FROM "{library()}"."{MARKER_TABLE}"')
        rows = cursor.fetchall()
    assert len(rows) == 1 and len(rows[0][0].rstrip()) == 32 and rows[0][1] is None
    Author.objects.create(name="in the test library")
    assert Author.objects.count() == 1
    connection.creation.destroy_test_db(library(), verbosity=0, keepdb=False)
    assert tables() == set()


def test_keepdb_reuses_and_next_clean_run_recovers() -> None:
    creation = connection.creation
    creation.create_test_db(verbosity=0, autoclobber=True, keepdb=False)
    Author.objects.create(name="kept")
    creation.create_test_db(verbosity=0, autoclobber=False, keepdb=True)
    assert Author.objects.count() == 1  # reused, not recreated
    # A crashed run: no destroy. The next clean run drops its tables.
    creation.create_test_db(verbosity=0, autoclobber=True, keepdb=False)
    assert Author.objects.count() == 0
    creation.destroy_test_db(library(), verbosity=0, keepdb=False)


def test_foreign_table_is_refused() -> None:
    foreign = f'"{library()}"."DJFOREIGN"'
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE {foreign} (ID INTEGER)")
    try:
        with pytest.raises(TestDatabaseRefused, match="DJFOREIGN"):
            connection.creation.create_test_db(verbosity=0, autoclobber=True, keepdb=False)
        assert tables() == {"DJFOREIGN"}  # nothing changed, no marker
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE {foreign}")


def test_model_tables_without_marker_are_refused() -> None:
    with connection.schema_editor() as editor:
        editor.create_model(Author)
    try:
        with pytest.raises(TestDatabaseRefused, match="may be a production library"):
            connection.creation.create_test_db(verbosity=0, autoclobber=True, keepdb=False)
        assert tables() == {"TESTAPP_AUTHOR"}  # nothing changed, no marker
    finally:
        with connection.schema_editor() as editor:
            editor.delete_model(Author)
