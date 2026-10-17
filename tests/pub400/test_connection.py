"""Smoke check: Django's connection.cursor() against the configured IBM i.

No test database is created; the tests only run SELECT statements on the
single connection of the ``default`` alias (read-only).
"""

import pytest
from django.db import connection

from django_db2_for_i.drivers import pyodbc as pyodbc_driver


@pytest.fixture
def live(django_db_blocker):
    """Database access without test database setup (read-only checks)."""
    with django_db_blocker.unblock():
        yield connection


def test_select_one(live) -> None:
    with live.cursor() as cursor:
        cursor.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
        assert cursor.fetchone() == (1,)


def test_placeholders_and_percent(live) -> None:
    with live.cursor() as cursor:
        cursor.execute("SELECT CAST(%s AS INTEGER), '100%%' FROM SYSIBM.SYSDUMMY1", [42])
        assert cursor.fetchone() == (42, "100%")
        # Without params the SQL is sent as is.
        cursor.execute("SELECT '100%' FROM SYSIBM.SYSDUMMY1")
        assert cursor.fetchone() == ("100%",)


def test_session_state(live) -> None:
    with live.cursor() as cursor:
        cursor.execute("SELECT CURRENT SCHEMA FROM SYSIBM.SYSDUMMY1")
        assert cursor.fetchone()[0].rstrip() == live.settings_dict["NAME"].upper()
        cursor.execute(
            "SELECT DEFAULT_LOCK_LEVEL FROM QSYS2.DB_TRANSACTION_INFO "
            "WHERE JOB_NAME = QSYS2.JOB_NAME"
        )
        assert cursor.fetchone()[0].rstrip() == "*CS"
    assert live.get_autocommit() is True
    assert live.is_usable()


def test_capabilities_detected(live) -> None:
    live.ensure_connection()
    caps = live.capabilities
    assert caps.source.startswith("detected 07.05.")
    assert caps.release == (7, 5)
    assert live.get_database_version() == (7, 5)
    assert live.features.has_native_boolean_field is True


def test_flush_metadata_queries_run(live) -> None:
    # Read-only catalog queries used by sql_flush(); the table does not exist.
    assert live.ops._flush_metadata(["DJ_NO_SUCH_TABLE"]) == (set(), {})


def test_pagination_sql_runs(live) -> None:
    with live.cursor() as cursor:
        base = "SELECT X FROM (VALUES 1, 2, 3, 4) AS T (X) ORDER BY X "
        cursor.execute(base + live.ops.limit_offset_sql(1, None))
        assert cursor.fetchall() == [(2,), (3,), (4,)]
        cursor.execute(base + live.ops.limit_offset_sql(1, 3))
        assert cursor.fetchall() == [(2,), (3,)]
        cursor.execute(base + live.ops.limit_offset_sql(0, 2))
        assert cursor.fetchall() == [(1,), (2,)]


def test_long_strings_arrive_intact(live) -> None:
    """Strings past the old chunk boundaries (8185+ chars) and the maximum, 1M units."""
    sql = (
        "SELECT CHARACTER_LENGTH(CAST(%s AS NCLOB(1M))), CAST(%s AS NCLOB(1M)) "
        "FROM SYSIBM.SYSDUMMY1"
    )
    limit = pyodbc_driver.MAX_STRING_PARAM_UNITS
    with live.cursor() as cursor:
        for text in ["é" * 8185, "\U0001f600" * 12000, "x" * (limit - 1) + "€"]:
            cursor.execute(sql, [text, text])
            length, back = cursor.fetchone()
            # CHARACTER_LENGTH of an NCLOB counts characters (an emoji is one).
            assert (length, back == text) == (len(text), True)


def test_strings_over_the_maximum_are_refused(live) -> None:
    import django.db

    limit = pyodbc_driver.MAX_STRING_PARAM_UNITS
    with (
        live.cursor() as cursor,
        pytest.raises(django.db.NotSupportedError, match="longer than 1M characters"),
    ):
        cursor.execute("SELECT CAST(%s AS NCLOB(2M)) FROM SYSIBM.SYSDUMMY1", ["x" * (limit + 1)])
