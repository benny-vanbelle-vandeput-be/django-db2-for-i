"""Schema, introspection and operations against the IBM i (writes).

Creates the tests.testapp tables in the default library (journaled), runs
the checks and drops the tables again. Refuses to start if any of these
tables already exist, and never drops tables it did not create.

Foreign keys are enabled for this module only, to execute the NO ACTION
foreign key DDL and the DELETE path of sql_flush(); the feature flag itself
stays off until Django's test suite backs it.
"""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.db import connection, models
from django.db.models import Case, Count, Exists, F, Max, OuterRef, Q, Subquery, Value, When

from django_db2_for_i.drivers import pyodbc as pyodbc_driver
from tests.testapp.models import Author, Book, Defaults, Document, Node, Tag

MODELS = (Author, Book, Node, Tag, Defaults, Document)
TABLES = {model._meta.db_table for model in MODELS}


@pytest.fixture(scope="module", autouse=True)
def tables(django_db_blocker):
    with django_db_blocker.unblock(), pytest.MonkeyPatch.context() as patch:
        existing = TABLES & set(connection.introspection.table_names())
        if existing:
            pytest.fail(f"tables already exist, remove them first: {sorted(existing)}")
        patch.setattr(connection.features, "supports_foreign_keys", True)
        created = []
        try:
            with connection.schema_editor() as editor:
                for model in MODELS:
                    editor.create_model(model)
                    created.append(model)
            yield
        finally:
            errors = []
            for model in reversed(created):
                try:
                    with connection.schema_editor() as editor:
                        editor.delete_model(model)
                except Exception as exc:  # report every leftover table
                    errors.append(f"{model._meta.db_table}: {exc}")
            assert not errors, f"tables NOT dropped, remove manually: {errors}"


@pytest.fixture
def live(django_db_blocker):
    with django_db_blocker.unblock():
        yield connection


@pytest.fixture
def empty(live):
    """Empty all testapp tables (and restart identities) after the test."""
    yield
    live.ops.execute_sql_flush(live.ops.sql_flush(_style(), sorted(TABLES), reset_sequences=True))


def _style():
    from django.core.management.color import no_style

    return no_style()


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


def test_distinct_with_emulated_null_ordering(live, empty) -> None:
    """SELECT DISTINCT + nulls_first / nulls_last (hidden predicate column, compiler.py).

    Same rows as computed in Python, duplicates removed, and the hidden
    columns never reach model instances, values() or values_list().
    """
    one = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    two = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
    a1, a2, _ = (Author.objects.create(name=name) for name in ("a1", "a2", "a3"))
    for author, title, published in [
        (a1, "t1", None),
        (a1, "t1", None),  # duplicate row
        (a1, "t2", one),
        (a2, "t2", one),  # same (title, published) as the row before
        (a2, "t3", two),
    ]:
        Book.objects.create(author=author, title=title, published=published)

    first = F("published").asc(nulls_first=True)
    pairs = Book.objects.order_by(first, "title").distinct().values_list("title", "published")
    assert list(pairs) == [("t1", None), ("t2", one), ("t3", two)]
    last = F("published").desc(nulls_last=True)
    titles = Book.objects.order_by(last).distinct().values_list("title", flat=True)
    assert list(titles) == ["t3", "t2", "t1"]
    dicts = list(Book.objects.order_by(first, "title").distinct().values("title", "published"))
    assert dicts == [
        {"title": "t1", "published": None},
        {"title": "t2", "published": one},
        {"title": "t3", "published": two},
    ]

    # Django's own case: order authors by an annotated subquery, NULLs first.
    newest = (
        Book.objects.filter(author=OuterRef("pk"))
        .order_by()
        .values("author")
        .annotate(m=Max("published"))
        .values("m")
    )
    authors = (
        Author.objects.annotate(last=Subquery(newest, output_field=models.DateTimeField()))
        .order_by(F("last").asc(nulls_first=True), "name")
        .distinct()
    )
    assert [(a.name, a.last) for a in authors] == [("a3", None), ("a1", one), ("a2", two)]
    assert list(authors.values_list("name", "last")) == [
        ("a3", None),
        ("a1", one),
        ("a2", two),
    ]
    assert [sorted(row) for row in authors.values("name")] == [["name"]] * 3
    # With a parameter in the subquery (as in Django's ordering tests).
    newest_t = newest.filter(title__icontains="T")
    with_param = (
        Author.objects.annotate(last=Subquery(newest_t, output_field=models.DateTimeField()))
        .order_by(F("last").desc(nulls_last=True), "name")
        .distinct()
        .values_list("name", "last")
    )
    assert list(with_param) == [("a2", two), ("a1", one), ("a3", None)]


def test_exists_in_every_position(live, empty) -> None:
    """Exists(): EXISTS in WHERE, a first-row subquery elsewhere (compiler.py)."""
    a1, a2 = Author.objects.create(name="a1"), Author.objects.create(name="a2")
    Book.objects.create(author=a1, title="t")
    books = Exists(Book.objects.filter(author=OuterRef("pk")))
    by_id = Author.objects.order_by("id")
    assert list(by_id.filter(books)) == [a1]
    assert list(by_id.filter(~books)) == [a2]
    assert list(by_id.filter(Q(name="a2") | books)) == [a1, a2]
    assert list(by_id.annotate(has=books).values_list("name", "has")) == [
        ("a1", True),
        ("a2", False),
    ]
    assert list(by_id.annotate(has=~books).values_list("has", flat=True)) == [False, True]
    assert list(by_id.annotate(has=books).filter(has=False)) == [a2]
    case = Case(When(books, then=Value(1)), default=Value(0))
    assert list(by_id.annotate(x=case).values_list("x", flat=True)) == [1, 0]
    assert list(by_id.annotate(x=case).filter(x=1)) == [a1]
    assert list(Author.objects.order_by(books.desc(), "id")) == [a1, a2]
    grouped = Author.objects.annotate(has=books).values("has").annotate(n=Count("id"))
    assert sorted((row["has"], row["n"]) for row in grouped) == [(False, 1), (True, 1)]
    # Nested Exists with OuterRef(OuterRef()) (Django's lookup tests).
    nested = Exists(
        Book.objects.annotate(
            same=Exists(Author.objects.filter(name=OuterRef(OuterRef("name"))))
        ).filter(same=True)
    )
    assert Author.objects.filter(nested).count() == 2


def test_logged_queries_show_parameters(live, empty) -> None:
    """last_executed_query(): the logged SQL has the values (logging only)."""
    from django.test.utils import CaptureQueriesContext

    author = Author.objects.create(name="O'Brien")
    with CaptureQueriesContext(live) as ctx:
        assert list(Author.objects.filter(id__in=[None, author.id], name="O'Brien")) == [author]
    assert f"IN ({author.id})" in ctx.captured_queries[0]["sql"]
    assert "= 'O''Brien'" in ctx.captured_queries[0]["sql"]


def test_pagination(live, empty) -> None:
    for name in "abcde":
        Author.objects.create(name=name)
    names = Author.objects.order_by("id").values_list("name", flat=True)
    assert list(names[1:3]) == ["b", "c"]
    assert list(names[3:]) == ["d", "e"]
    assert list(names[:2]) == ["a", "b"]


# --- Identity reset and flush -----------------------------------------------------


def test_sequence_reset_after_explicit_keys(live, empty) -> None:
    Author.objects.create(id=50, name="explicit")
    with live.cursor() as cursor:
        for sql in live.ops.sequence_reset_sql(_style(), [Author]):
            cursor.execute(sql)
    assert Author.objects.create(name="next").pk == 51


def test_flush_with_foreign_keys(live) -> None:
    author = Author.objects.create(name="a")
    Book.objects.create(author=author, title="t")
    root = Node.objects.create()
    Node.objects.create(parent=root)
    statements = live.ops.sql_flush(_style(), sorted(TABLES), reset_sequences=True)
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


# --- Extracting date/time parts --------------------------------------------------------


def test_extract_values(live, empty) -> None:
    """Django's conventions on an ISO week edge: Sunday 2023-01-01 is ISO 2022-W52."""
    from django.db.models.functions import Extract

    author = Author.objects.create(name="a")
    Book.objects.create(
        author=author,
        title="t",
        published=dt.datetime(2023, 1, 1, 13, 45, 30, 123456, tzinfo=dt.UTC),
        reading_time=dt.time(6, 7, 8),
    )
    lookups = ("year", "iso_year", "quarter", "month", "week", "week_day", "iso_week_day")
    lookups += ("day", "hour", "minute", "second")
    values = Book.objects.values(**{lookup: Extract("published", lookup) for lookup in lookups})
    assert values.get() == {
        "year": 2023,
        "iso_year": 2022,
        "quarter": 1,
        "month": 1,
        "week": 52,
        "week_day": 1,
        "iso_week_day": 7,
        "day": 1,
        "hour": 13,
        "minute": 45,
        "second": 30,
    }
    assert Book.objects.filter(published__week_day=1, published__iso_week_day=7).count() == 1
    assert Book.objects.filter(reading_time__second=8).count() == 1
