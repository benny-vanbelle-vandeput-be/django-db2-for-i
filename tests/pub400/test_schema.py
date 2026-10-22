"""Schema, introspection and operations against the IBM i (writes).

The tests.testapp tables are created for this module and dropped again
(``testapp_tables`` in conftest.py).
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.core.management.color import no_style
from django.db import models

from django_db2_for_i.drivers import pyodbc as pyodbc_driver
from tests.pub400.testapp_tables import MODELS, TABLES
from tests.testapp.models import Article, Author, Book, Defaults, Document, Node, Tag

pytestmark = pytest.mark.usefixtures("testapp_tables")


# --- Introspection ------------------------------------------------------------


def test_table_list(live) -> None:
    tables = {info.name: info.type for info in live.introspection.get_table_list(live.cursor())}
    assert {table: tables.get(table) for table in TABLES} == dict.fromkeys(TABLES, "t")
    # The SQL catalog views Db2 creates in a library with constraints are not listed.
    assert "syscst" not in tables


def test_table_description(live) -> None:
    with live.cursor() as cursor:
        description = live.introspection.get_table_description(cursor, "testapp_book")
    columns = {info.name: info for info in description}
    assert list(columns) == [
        "id",
        "author_id",
        "title",
        "published",
        "reading_time",
        "available",
        "pages",
    ]
    assert columns["published"].null_ok is True
    assert columns["title"].null_ok is False


def test_column_order_follows_field_creation_order(live) -> None:
    """Issue #23: the table's columns are _meta.local_fields, in order, for a model
    with fields from an abstract mixin and an abstract base, in the catalog and
    in introspection."""
    expected = [field.column for field in Article._meta.local_fields]
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
            [Article._meta.db_table.upper()],
        )
        catalog = [row[0].rstrip() for row in cursor.fetchall()]
        description = live.introspection.get_table_description(cursor, Article._meta.db_table)
    assert catalog == [column.upper() for column in expected]
    assert [info.name for info in description] == expected


def test_sequences(live) -> None:
    with live.cursor() as cursor:
        assert live.introspection.get_sequences(cursor, "testapp_node") == [
            {"table": "testapp_node", "column": "id"}
        ]
        assert live.introspection.get_sequences(cursor, "testapp_tag") == []


def test_foreign_keys_are_no_action(live) -> None:
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT C.TABLE_NAME, R.DELETE_RULE FROM QSYS2.SYSREFCST R "
            "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA "
            "AND C.CONSTRAINT_NAME = R.CONSTRAINT_NAME "
            "WHERE C.TABLE_SCHEMA = CURRENT SCHEMA AND C.TABLE_NAME IN (%s, %s) "
            "ORDER BY C.TABLE_NAME",
            ["TESTAPP_BOOK", "TESTAPP_NODE"],
        )
        rows = [(table.rstrip(), rule.rstrip()) for table, rule in cursor.fetchall()]
    assert rows == [("TESTAPP_BOOK", "NO ACTION"), ("TESTAPP_NODE", "NO ACTION")]


# --- Inserts, values, pagination -------------------------------------------------


def test_insert_returns_identity(live, empty) -> None:
    first = Author.objects.create(name="Ada")
    second = Author.objects.create(name="Grace")
    assert (first.pk, second.pk) == (1, 2)
    assert type(first.pk) is int


def test_values_round_trip(live, empty) -> None:
    author = Author.objects.create(name="Ångström \U0001f600")
    published = dt.datetime(
        2026, 10, 17, 15, 30, 0, 123456, tzinfo=dt.timezone(dt.timedelta(hours=2))
    )
    book = Book.objects.create(
        author=author,
        title="Db2",
        published=published,
        reading_time=dt.time(1, 2, 3, 456789),
        available=False,
        pages=10,
    )
    book = Book.objects.get(pk=book.pk)
    assert Author.objects.get(pk=author.pk).name == "Ångström \U0001f600"
    assert book.published == published
    assert book.published.tzinfo is not None
    assert book.reading_time == dt.time(1, 2, 3)  # microseconds truncated
    assert book.available is False
    # Lookups use the same truncation as saving.
    assert Book.objects.filter(reading_time=dt.time(1, 2, 3, 456789)).count() == 1
    tag = Tag.objects.create(label="db2")
    assert Tag.objects.get(label="db2").pk == tag.pk


@pytest.mark.parametrize(
    "text",
    [
        "é" * 8185,  # past the first old chunk boundary
        "\U0001f600" * 20000,  # surrogate pairs across chunk boundaries
        "x" * (pyodbc_driver.MAX_STRING_PARAM_UNITS - 1) + "€",  # the maximum, 1M units
    ],
    ids=["8185 accented", "20000 emoji", "1M units"],
)
def test_long_text_and_binary_round_trip(live, empty, text) -> None:
    data = bytes(range(256)) * 4096  # 1 MiB, the BLOB column's capacity
    pk = Document.objects.create(text=text, data=data).pk
    document = Document.objects.get(pk=pk)
    assert len(document.text) == len(text)
    assert document.text == text
    assert bytes(document.data) == data


def test_non_ascii_comments(live) -> None:
    """COMMENT ON through Django's path (quote_value: a plain '...' constant).

    supports_comments stays off; this checks the statements the flag would emit.
    Characters of the job CCSID (273 on PUB400) work, quotes included. Others
    (euro sign, emoji) make the constant a graphic one, which COMMENT ON
    rejects (SQL0104, docs/IBMI_NOTES.md).
    """
    import django.db

    table = Document._meta.db_table.upper()  # catalog names are upper case
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(live.features, "supports_comments", True)
        with live.schema_editor() as editor:
            editor.alter_db_table_comment(Document, None, "Grüße, O'Brien")
            field = Document._meta.get_field("text")
            editor.execute(editor._alter_column_comment_sql(Document, field, None, "Ä Ö Ü ß é")[0])
        with (
            pytest.raises(django.db.ProgrammingError, match="SQL0104"),
            live.schema_editor() as editor,
        ):
            editor.alter_db_table_comment(Document, None, "Grüße €")
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT LONG_COMMENT FROM QSYS2.SYSTABLES "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s",
            [table],
        )
        assert cursor.fetchone() == ("Grüße, O'Brien",)
        cursor.execute(
            "SELECT LONG_COMMENT FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s AND COLUMN_NAME = 'TEXT'",
            [table],
        )
        assert cursor.fetchone() == ("Ä Ö Ü ß é",)


# --- Identity reset and flush -----------------------------------------------------


def test_sequence_reset_after_explicit_keys(live, empty) -> None:
    Author.objects.create(id=50, name="explicit")
    with live.cursor() as cursor:
        for sql in live.ops.sequence_reset_sql(no_style(), [Author]):
            cursor.execute(sql)
    assert Author.objects.create(name="next").pk == 51


def test_flush_with_foreign_keys(live) -> None:
    author = Author.objects.create(name="a")
    Book.objects.create(author=author, title="t")
    root = Node.objects.create()
    Node.objects.create(parent=root)
    statements = live.ops.sql_flush(no_style(), sorted(TABLES), reset_sequences=True)
    # Referenced tables (author, node) are deleted, the others truncated.
    assert 'DELETE FROM "TESTAPP_AUTHOR"' in statements
    assert 'DELETE FROM "TESTAPP_NODE"' in statements
    assert 'TRUNCATE TABLE "TESTAPP_BOOK" RESTART IDENTITY' in statements
    live.ops.execute_sql_flush(statements)
    assert [m.objects.count() for m in MODELS] == [0] * len(MODELS)
    assert Author.objects.create(name="b").pk == 1
    assert Node.objects.create().pk == 1
    live.ops.execute_sql_flush(statements)


# --- Column defaults ---------------------------------------------------------------


def test_db_defaults_are_stored_as_written(live, empty) -> None:
    """Every prepare_default() literal reaches the row unchanged (also "%")."""
    with live.cursor() as cursor:
        cursor.execute('INSERT INTO "TESTAPP_DEFAULTS" ("NOTHING") VALUES (NULL)')
    row = Defaults.objects.get()
    assert (row.text, row.flag, row.number, row.amount, row.ratio) == (
        "O'Brien 100%",
        True,
        -1,
        Decimal("1.50"),
        1.5,
    )
    assert (row.day, row.clock) == (dt.date(2026, 1, 2), dt.time(13, 45, 30))
    assert row.stamp == dt.datetime(2026, 1, 2, 13, 45, 30, 123456, tzinfo=dt.UTC)
    assert bytes(row.data) == b"\x01\xab"
    assert row.code == uuid.UUID("12345678-1234-5678-1234-567812345678")
    assert row.nothing is None


def test_add_not_null_field_with_python_default(live, empty) -> None:
    """Existing rows get the literal default; the column keeps no default.

    The column is not removed again: DROP COLUMN on a table with rows is
    cancelled by CPA32B2 (HY008, docs/IBMI_NOTES.md); the module fixture drops
    the table.
    """
    with live.cursor() as cursor:
        cursor.execute('INSERT INTO "TESTAPP_DEFAULTS" ("NOTHING") VALUES (NULL)')
    field = models.CharField(max_length=20, default="O'Brien")
    field.set_attributes_from_name("nickname")
    with live.schema_editor() as editor:
        editor.add_field(Defaults, field)
    with live.cursor() as cursor:
        cursor.execute('SELECT "NICKNAME" FROM "TESTAPP_DEFAULTS"')
        assert cursor.fetchall() == [("O'Brien",)]
        cursor.execute(
            "SELECT HAS_DEFAULT FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = CURRENT SCHEMA "
            "AND TABLE_NAME = 'TESTAPP_DEFAULTS' AND COLUMN_NAME = 'NICKNAME'"
        )
        assert cursor.fetchone()[0] == "N"
