"""Smoke check: Django's connection.cursor() against the configured IBM i.

No test database is created; the tests run SELECT statements on the single
connection of the ``default`` alias, and write only to a QTEMP table.
"""

import pytest
from django.db import ProgrammingError, connection

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


def test_trailing_semicolon(live) -> None:
    """One trailing ";" is removed (SQL0104 otherwise); a ";" in a literal stays."""
    with live.cursor() as cursor:
        cursor.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1; ")
        assert cursor.fetchone() == (1,)
        cursor.execute("SELECT CAST(%s AS INTEGER), ';' FROM SYSIBM.SYSDUMMY1;", [7])
        assert cursor.fetchone() == (7, ";")
        with pytest.raises(ProgrammingError, match="SQL0104"):
            cursor.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1;;")


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


def test_non_ascii_statement_text(live) -> None:
    """Literals, comments and parameters with non-ASCII characters (UTF-8 statement text)."""
    with live.cursor() as cursor:
        cursor.execute("SELECT N'é€\U0001f600', 'éÄß' FROM SYSIBM.SYSDUMMY1 -- Grüße")
        assert cursor.fetchone() == ("é€\U0001f600", "éÄß")
        cursor.execute(
            "SELECT N'Ångström', CAST(%s AS NVARCHAR(10)) FROM SYSIBM.SYSDUMMY1", ["€\U0001f600"]
        )
        assert cursor.fetchone() == ("Ångström", "€\U0001f600")


@pytest.fixture
def job_ccsid_table(live):
    """A QTEMP table with a VARCHAR column in the job CCSID (273 on PUB400)."""
    with live.cursor() as cursor:
        cursor.execute(
            "DECLARE GLOBAL TEMPORARY TABLE SESSION.DJVC (K INTEGER, V VARCHAR(10)) "
            "ON COMMIT PRESERVE ROWS WITH REPLACE"
        )
    yield "SESSION.DJVC"
    with live.cursor() as cursor:
        cursor.execute("DROP TABLE SESSION.DJVC")


def test_varchar_in_the_job_ccsid(live, job_ccsid_table) -> None:
    import django.db

    with live.cursor() as cursor:
        cursor.execute(f"INSERT INTO {job_ccsid_table} VALUES (1, %s)", ["éÄß"])
        cursor.execute(f"INSERT INTO {job_ccsid_table} VALUES (2, 'éÄß')")
        cursor.execute(f"SELECT V FROM {job_ccsid_table} ORDER BY K")
        assert cursor.fetchall() == [("éÄß",), ("éÄß",)]
        # A character the column's CCSID cannot hold is refused, not replaced.
        with pytest.raises(django.db.DataError, match="22018"):
            cursor.execute(f"INSERT INTO {job_ccsid_table} VALUES (3, %s)", ["€"])


def test_non_ascii_names_in_description_and_errors(live) -> None:
    """Correct with pooling off (the driver's setting) in a UTF-8 process locale."""
    import django.db

    with live.cursor() as cursor:
        cursor.execute('SELECT 1 AS "ÄÖÜ" FROM SYSIBM.SYSDUMMY1')
        assert cursor.description[0][0] == "ÄÖÜ"
        with pytest.raises(django.db.ProgrammingError, match='"ÄÖÜX" in QTEMP'):
            cursor.execute('SELECT * FROM QTEMP."ÄÖÜX"')


@pytest.mark.parametrize(
    "text", ["O'Brien's", "''", "Grüße, O'Brien", "€ \U0001f600 'quoted'"], ids=repr
)
def test_quote_value_literal_round_trip(live, text) -> None:
    """The schema editor's string literal reads back unchanged (quotes, non-ASCII)."""
    with live.schema_editor(collect_sql=True) as editor:
        literal = editor.quote_value(text)
    with live.cursor() as cursor:
        cursor.execute(f"SELECT {literal} FROM SYSIBM.SYSDUMMY1")
        assert cursor.fetchone() == (text,)


def test_journal_check_passes_on_the_test_library(live) -> None:
    """The system check django_db2_for_i.W001 reads the library's journaling
    state (read-only); the default library has a QSQJRN journal."""
    assert live.validation.check() == []


def test_journal_check_reads_both_sources(live) -> None:
    from django_db2_for_i.validation import _journaling_sql

    library = live.settings_dict["NAME"].upper()
    with live.cursor() as cursor:
        cursor.execute(_journaling_sql(library))
        journaled, inherit, _, _, qsqjrn = cursor.fetchone()
        assert (journaled.strip(), inherit.strip(), qsqjrn) == ("NO", "NO", 1)
        cursor.execute(_journaling_sql("DJDB2INONE"))
        assert cursor.fetchone() is None
