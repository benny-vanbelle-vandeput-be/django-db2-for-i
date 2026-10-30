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

from django_db2_for_i import compat
from django_db2_for_i.drivers import pyodbc as pyodbc_driver
from tests import table_registry
from tests.ibmi.connection_guard import replace_if_unusable
from tests.ibmi.testapp_tables import MODELS, TABLES
from tests.testapp.models import Article, Author, Book, Defaults, Document, Node, Rating, Tag

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


def test_constraints(live) -> None:
    """get_constraints() on a table with a primary key, a foreign key, a column
    check and two indexes; the primary key and the check have names Db2 chose."""
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, "testapp_book")
        primary_key = live.introspection.get_primary_key_column(cursor, "testapp_book")
        tag = live.introspection.get_constraints(cursor, "testapp_tag")
        account = live.introspection.get_constraints(cursor, "testapp_account")

    def kinds(found: dict) -> list[tuple]:
        return sorted(
            (
                entry["columns"],
                entry["primary_key"],
                entry["unique"],
                entry["foreign_key"] or (),
                entry["check"],
                entry["index"],
            )
            for entry in found.values()
        )

    assert kinds(constraints) == [
        (["author_id"], False, False, (), False, True),
        (["author_id"], False, False, ("testapp_author", "id"), False, False),
        (["id"], True, True, (), False, False),
        (["pages"], False, False, (), True, False),
        (["title"], False, False, (), False, True),
    ]
    assert primary_key == "id"
    index = constraints["testapp_book_title_c797b345"]
    assert (index["orders"], index["type"]) == (["ASC"], "idx")
    assert sorted(entry["columns"] for entry in tag.values() if entry["unique"]) == [
        ["id"],
        ["label"],
    ]
    assert ["company", "number"] in [entry["columns"] for entry in account.values()]


def test_relations(live) -> None:
    """get_relations() on the tier's foreign keys (Db2's default NO ACTION),
    including a self-reference, in the shape of the running Django version."""
    with live.cursor() as cursor:
        book = live.introspection.get_relations(cursor, "testapp_book")
        node = live.introspection.get_relations(cursor, "testapp_node")
        tag = live.introspection.get_relations(cursor, "testapp_tag")
    assert book == {"author_id": compat.relation("id", "testapp_author", "NO ACTION")}
    assert node == {"parent_id": compat.relation("id", "testapp_node", "NO ACTION")}
    assert tag == {}


def test_field_types(live) -> None:
    """get_field_type() on the catalog's types: what inspectdb would write back
    for the tier's tables (identities as AutoFields, UUIDField as CHAR(32))."""
    expected = {
        "testapp_book": {
            "id": "BigAutoField",
            "author_id": "IntegerField",
            "title": "CharField",
            "published": "DateTimeField",
            "reading_time": "TimeField",
            "available": "BooleanField",
            "pages": "IntegerField",
        },
        "testapp_node": {"id": "SmallAutoField", "parent_id": "SmallIntegerField"},
        "testapp_tag": {"id": "CharField", "label": "CharField"},
        "testapp_document": {"id": "AutoField", "text": "TextField", "data": "BinaryField"},
        "testapp_schedule": {
            "id": "AutoField",
            "start": "DateTimeField",
            "day": "DateField",
            "clock": "TimeField",
            "length": "BigIntegerField",
        },
        "testapp_measure": {
            "id": "AutoField",
            "small": "SmallIntegerField",
            "amount": "DecimalField",
            "big": "BigIntegerField",
        },
    }
    found = {}
    with live.cursor() as cursor:
        for table in expected:
            rows = live.introspection.get_table_description(cursor, table)
            found[table] = {r.name: live.introspection.get_field_type(r.type_code, r) for r in rows}
            sizes = {r.name: (r.display_size, r.precision, r.scale) for r in rows}
            if table == "testapp_book":
                assert sizes["title"][0] == 200
            if table == "testapp_measure":
                assert sizes["amount"][1:] == (5, 2)
            if table == "testapp_tag":
                assert sizes["id"][0] == 32
    assert found == expected


def test_column_defaults(live) -> None:
    """FieldInfo.default is COLUMN_DEFAULT as Db2 for i records it, the literal
    as the backend wrote it; None for a column without a default."""
    with live.cursor() as cursor:
        rows = live.introspection.get_table_description(cursor, Defaults._meta.db_table)
    defaults = {r.name: r.default for r in rows}
    assert defaults["id"] is None
    assert defaults["number"] == "-1"
    assert defaults["flag"] == "TRUE"
    assert defaults["amount"] == "1.50"
    # The backend writes NVARCHAR literals as UX'<UTF-16 hex>' (any text
    # survives the job CCSID); Db2 for i records the literal as written.
    assert defaults["text"] == "UX'" + "O'Brien 100%".encode("utf-16-be").hex().upper() + "'"
    for column in ("ratio", "day", "clock", "stamp", "data", "code"):
        assert defaults[column] not in (None, "NULL"), column
    assert defaults["nothing"] in (None, "NULL")


def test_inspectdb(live, monkeypatch) -> None:
    """The common use of introspection: inspectdb writes models for existing
    tables, with types, lengths, nullability and the foreign key. On 6.1
    inspectdb needs supports_inspectdb (step D); it is switched on here only."""
    import io

    from django.core.management import call_command

    monkeypatch.setattr(live.features, "supports_inspectdb", True)
    out = io.StringIO()
    call_command("inspectdb", "testapp_author", "testapp_book", stdout=out)
    lines = [line.strip() for line in out.getvalue().splitlines()]
    for line in (
        "class TestappAuthor(models.Model):",
        "name = models.CharField(max_length=100)",
        "class TestappBook(models.Model):",
        "id = models.BigAutoField(primary_key=True)",
        "author = models.ForeignKey(TestappAuthor, models.DO_NOTHING)",
        "title = models.CharField(max_length=200)",
        "published = models.DateTimeField(blank=True, null=True)",
        "reading_time = models.TimeField(blank=True, null=True)",
        "available = models.BooleanField()",
        "pages = models.IntegerField()",
        "db_table = 'testapp_book'",
    ):
        assert line in lines, (line, out.getvalue())


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


# --- AlterField ---------------------------------------------------------------------

ALTER_COLUMNS = (
    "SELECT COLUMN_NAME, DATA_TYPE, LENGTH, NUMERIC_SCALE, IS_NULLABLE, COLUMN_DEFAULT "
    "FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = CURRENT SCHEMA "
    "AND TABLE_NAME = 'TESTAPP_ALTERFIELD' AND COLUMN_NAME IN ('TEXT', 'NUMBER', 'AMOUNT') "
    "ORDER BY COLUMN_NAME"
)
ALTER_ROWS = 'SELECT "ID", "TEXT", "NUMBER", "AMOUNT" FROM "TESTAPP_ALTERFIELD" ORDER BY "ID"'


@pytest.fixture
def alter_model(live):
    """A model of its own (testapp_alterfield), so the ALTERs meet no column
    another test added; created for the test and dropped after it."""
    from django.apps import apps

    class AlterField(models.Model):
        text = models.CharField(max_length=20, db_default="O'Brien 100%")
        number = models.IntegerField(db_default=-1)
        amount = models.DecimalField(max_digits=5, decimal_places=2, db_default=Decimal("1.50"))

        class Meta:
            app_label = "testapp"

    try:
        with live.schema_editor() as editor:
            editor.create_model(AlterField)
        yield AlterField
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute('DROP TABLE "TESTAPP_ALTERFIELD"')
        apps.all_models["testapp"].pop("alterfield", None)
        apps.clear_cache()


def _rebuilt(model, name, cls=None, **changes):
    """``model``'s field rebuilt with ``changes``, as a migration's AlterField has it."""
    old = model._meta.get_field(name)
    _name, _path, args, kwargs = old.deconstruct()
    field = (cls or type(old))(*args, **{**kwargs, **changes})
    field.set_attributes_from_name(name)
    field.model = model
    return field


def _stripped(rows) -> list[tuple]:
    return [tuple(v.rstrip() if isinstance(v, str) else v for v in row) for row in rows]


def _ux(text: str) -> str:
    return "UX'" + text.encode("utf-16-be").hex().upper() + "'"


def test_alter_field_and_back(live, alter_model) -> None:
    """A migration that widens columns, makes one nullable and changes a default,
    and its way back.

    Forward: SET DATA TYPE (widening), DROP NOT NULL and SET DEFAULT work on a
    table with rows, and the rows keep their values. Back: narrowing and NOT NULL
    send CPA32B2, which the schema editor suppresses for its job (inquiry.py).
    A narrowing that would truncate a value is refused first, and the table is
    unchanged; the way back to the original lengths works. The way back to NOT
    NULL first sets the NULL to the default (Django's UPDATE before SET NOT
    NULL): in a transaction that fails with SQL0910, without one it works.
    """
    from django.db import DatabaseError, DataError

    model = alter_model
    with live.cursor() as cursor:
        cursor.execute(
            'INSERT INTO "TESTAPP_ALTERFIELD" ("TEXT", "NUMBER", "AMOUNT") '
            "VALUES ('first', 7, 123.45)"
        )
        cursor.execute('INSERT INTO "TESTAPP_ALTERFIELD" ("NUMBER") VALUES (DEFAULT)')
    text, number, amount = (_rebuilt(model, name) for name in ("text", "number", "amount"))
    wide_text = _rebuilt(model, "text", max_length=40, db_default="Ж € ✓")
    wide_number = _rebuilt(model, "number", models.BigIntegerField, null=True)
    wide_amount = _rebuilt(model, "amount", max_digits=7, decimal_places=3)
    with live.schema_editor() as editor:
        editor.alter_field(model, text, wide_text, strict=True)
        editor.alter_field(model, number, wide_number, strict=True)
        editor.alter_field(model, amount, wide_amount, strict=True)

    forward = [
        ("AMOUNT", "DECIMAL", 7, 3, "N", "1.50"),
        ("NUMBER", "BIGINT", 8, 0, "Y", "-1"),
        ("TEXT", "VARG", 40, None, "N", _ux("Ж € ✓")),
    ]
    rows = [
        (1, "first", 7, Decimal("123.450")),
        (2, "O'Brien 100%", -1, Decimal("1.500")),
    ]
    with live.cursor() as cursor:
        cursor.execute(ALTER_COLUMNS)
        assert _stripped(cursor.fetchall()) == forward
        cursor.execute(ALTER_ROWS)
        assert [tuple(row) for row in cursor.fetchall()] == rows
        # The new default, and a NULL the column now accepts: the way back
        # (NOT NULL) would first set it to the default.
        cursor.execute('INSERT INTO "TESTAPP_ALTERFIELD" ("NUMBER") VALUES (NULL)')
    rows.append((3, "Ж € ✓", None, Decimal("1.500")))

    # "O'Brien 100%" has 12 characters.
    with (
        pytest.raises(DataError, match="longer than 10 UTF-16 code units"),
        live.schema_editor() as editor,
    ):
        editor.alter_field(model, wide_text, _rebuilt(model, "text", max_length=10))
    with live.cursor() as cursor:
        cursor.execute(ALTER_COLUMNS)
        assert _stripped(cursor.fetchall()) == forward
        cursor.execute(ALTER_ROWS)
        assert [tuple(row) for row in cursor.fetchall()] == rows

    with live.schema_editor() as editor:
        editor.alter_field(model, wide_text, text, strict=True)
    back_text = [*forward[:2], ("TEXT", "VARG", 20, None, "N", _ux("O'Brien 100%"))]
    # Back to NOT NULL: Django sets the NULL to the default (UPDATE), then SET
    # NOT NULL. In one transaction Db2 for i refuses the ALTER TABLE after the
    # row change (SQL0910), and the transaction is rolled back; without a
    # transaction (atomic = False) it works.
    with pytest.raises(DatabaseError, match="SQL0910"), live.schema_editor() as editor:
        editor.alter_field(model, wide_number, number, strict=True)
    with live.cursor() as cursor:
        cursor.execute(ALTER_COLUMNS)
        assert _stripped(cursor.fetchall()) == back_text
        cursor.execute(ALTER_ROWS)
        assert [tuple(row) for row in cursor.fetchall()] == rows
    with live.schema_editor(atomic=False) as editor:
        editor.alter_field(model, wide_number, number, strict=True)
    with live.cursor() as cursor:
        cursor.execute(ALTER_COLUMNS)
        assert _stripped(cursor.fetchall()) == [
            ("AMOUNT", "DECIMAL", 7, 3, "N", "1.50"),
            ("NUMBER", "INTEGER", 4, 0, "N", "-1"),
            ("TEXT", "VARG", 20, None, "N", _ux("O'Brien 100%")),
        ]
        cursor.execute(ALTER_ROWS)
        assert [tuple(row) for row in cursor.fetchall()] == [
            *rows[:2],
            (3, "Ж € ✓", -1, Decimal("1.500")),
        ]
    assert not live._inquiry_override_pending


# --- Renames and identity changes ---------------------------------------------------


@pytest.fixture
def rename_model(live):
    """A model of its own (testapp_renameprobe) with an integer primary key and a
    named index; created for the test and dropped after it. The test renames the
    table back before it ends; bin/ibmi-cleanup's list follows each rename."""
    from django.apps import apps

    class RenameProbe(models.Model):
        id = models.IntegerField(primary_key=True)
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "testapp"
            indexes = (models.Index(fields=["name"], name="testapp_rp_name_idx"),)

    try:
        with live.schema_editor() as editor:
            editor.create_model(RenameProbe)
        yield RenameProbe
    finally:
        replace_if_unusable(live)
        RenameProbe._meta.db_table = "testapp_renameprobe"
        with live.cursor() as cursor:
            cursor.execute('DROP TABLE "TESTAPP_RENAMEPROBE"')
        apps.all_models["testapp"].pop("renameprobe", None)
        apps.clear_cache()


def _index_names(live, table: str) -> set[str]:
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, table)
    return {name for name, info in constraints.items() if info["index"]}


RENAME_NAMES = ("TESTAPP_RENAMEPROBE", "TESTAPP_RENAMED_PROBE")


def _current(live) -> tuple[str, tuple[str, ...]]:
    """(name, renamed_from) of the rename probe table's newest cleanup list
    entry, the one a rename updates (older entries of earlier runs may stay
    pending: a rolled-back rename keeps both names)."""
    library = live.settings_dict["NAME"].upper()
    entries = [
        entry
        for entry in table_registry.read(table_registry.list_path())
        if entry.library == library and entry.names & set(RENAME_NAMES)
    ]
    return entries[-1].name, entries[-1].renamed_from


def test_rename_table_index_and_identity(live, rename_model) -> None:
    """RenameIndex, IntegerField -> AutoField on a table with rows (the identity
    continues after the largest key), RenameModel with the ORM working on the new
    name, and AutoField -> IntegerField (DROP IDENTITY: no generated keys).

    The cleanup list follows the renames (CLAUDE.md, bin/ibmi-cleanup): while
    each RENAME TABLE runs its entry holds both names, after the schema
    editor's transaction commits only the new one; after the rename back only
    the old one. The checks look at the table's newest entry, the one a rename
    updates.
    """
    from django.db import IntegrityError

    assert table_registry.list_path() is not None, "IBM i runs go through scripts/pub400.sh"
    old, new = RENAME_NAMES
    during = []

    def capture(execute, sql, params, many, context):
        # Inside the list's own wrapper: the list as the statement runs.
        if sql.lstrip().upper().startswith("RENAME TABLE"):
            during.append(_current(live))
        return execute(sql, params, many, context)

    model = rename_model
    model.objects.bulk_create([model(id=1, name="one"), model(id=2, name="two")])

    old_index, new_index = (
        model._meta.indexes[0],
        models.Index(fields=["name"], name="testapp_rp_label_idx"),
    )
    with live.schema_editor() as editor:
        editor.rename_index(model, old_index, new_index)
    assert "testapp_rp_label_idx" in _index_names(live, "testapp_renameprobe")
    assert "testapp_rp_name_idx" not in _index_names(live, "testapp_renameprobe")

    plain = model._meta.get_field("id")
    auto = models.AutoField(primary_key=True)
    auto.set_attributes_from_name("id")
    auto.model = model
    with live.schema_editor() as editor:
        editor.alter_field(model, plain, auto, strict=True)
    with live.cursor() as cursor:
        cursor.execute('INSERT INTO "TESTAPP_RENAMEPROBE" ("NAME") VALUES (%s)', ["three"])

    assert _current(live) == (old, ())
    try:
        with live.execute_wrapper(capture), live.schema_editor() as editor:
            editor.alter_db_table(model, "testapp_renameprobe", "testapp_renamed_probe")
        model._meta.db_table = "testapp_renamed_probe"
        assert during[0] == (new, (old,))
        assert _current(live) == (new, ())
        assert list(model.objects.order_by("id").values_list("id", "name")) == [
            (1, "one"),
            (2, "two"),
            (3, "three"),
        ]
        assert model.objects.get(name="two").pk == 2
        assert "testapp_rp_label_idx" in _index_names(live, "testapp_renamed_probe")
        with live.cursor() as cursor:
            cursor.execute('INSERT INTO "TESTAPP_RENAMED_PROBE" ("NAME") VALUES (%s)', ["four"])
            cursor.execute('SELECT "ID" FROM "TESTAPP_RENAMED_PROBE" WHERE "NAME" = %s', ["four"])
            assert cursor.fetchone() == (4,)
    finally:
        if model._meta.db_table != "testapp_renameprobe":
            with live.execute_wrapper(capture), live.schema_editor() as editor:
                editor.alter_db_table(model, "testapp_renamed_probe", "testapp_renameprobe")
            model._meta.db_table = "testapp_renameprobe"
    assert during[1] == (old, (new,))
    assert _current(live) == (old, ())

    with live.schema_editor() as editor:
        editor.alter_field(model, auto, plain, strict=True)
    model.objects.create(id=10, name="explicit")
    with pytest.raises(IntegrityError), live.cursor() as cursor:
        cursor.execute('INSERT INTO "TESTAPP_RENAMEPROBE" ("NAME") VALUES (%s)', ["no key"])


def _tables(live, *names: str) -> set[str]:
    """Which of ``names`` exist in the library (as this connection sees them)."""
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = CURRENT SCHEMA "
            f"AND TABLE_NAME IN ({', '.join(['%s'] * len(names))})",
            list(names),
        )
        return {row[0] for row in cursor.fetchall()}


class _Rollback(Exception):
    pass


def test_rename_rolled_back_keeps_both_names(live, rename_model) -> None:
    """A RENAME TABLE in a transaction that is rolled back: the table has its
    old name again, and its cleanup list entry keeps both names (CLAUDE.md,
    bin/ibmi-cleanup: cleared only after the commit)."""
    from django.db import transaction

    old, new = RENAME_NAMES
    with pytest.raises(_Rollback), transaction.atomic():
        with live.schema_editor() as editor:
            editor.alter_db_table(rename_model, "testapp_renameprobe", "testapp_renamed_probe")
        assert _tables(live, old, new) == {new}
        assert _current(live) == (new, (old,))
        raise _Rollback
    assert _tables(live, old, new) == {old}
    assert _current(live) == (new, (old,))


def test_rename_in_a_rolled_back_savepoint_keeps_both_names(live, rename_model) -> None:
    """A RENAME TABLE in a nested atomic() whose savepoint is rolled back while
    the outer transaction commits: ROLLBACK TO SAVEPOINT undoes the rename, and
    Django discards the on_commit callback registered in the savepoint, so the
    entry keeps both names after the commit."""
    from django.db import transaction

    old, new = RENAME_NAMES
    with transaction.atomic():
        with pytest.raises(_Rollback), transaction.atomic():
            with live.schema_editor() as editor:
                editor.alter_db_table(rename_model, "testapp_renameprobe", "testapp_renamed_probe")
            assert _tables(live, old, new) == {new}
            raise _Rollback
        assert _tables(live, old, new) == {old}
        assert live.run_on_commit == []
    assert _tables(live, old, new) == {old}
    assert _current(live) == (new, (old,))


def test_rename_without_a_transaction_clears_the_entry_at_once(live, rename_model) -> None:
    """atomic = False (autocommit): the entry holds only the new name as soon
    as the statement succeeded, and only the old one after the rename back."""
    old, new = RENAME_NAMES
    try:
        with live.schema_editor(atomic=False) as editor:
            editor.alter_db_table(rename_model, "testapp_renameprobe", "testapp_renamed_probe")
            assert _current(live) == (new, ())
            assert not live.in_atomic_block
    finally:
        if _tables(live, old, new) == {new}:
            with live.schema_editor(atomic=False) as editor:
                editor.alter_db_table(rename_model, "testapp_renamed_probe", "testapp_renameprobe")
    assert _current(live) == (old, ())


# --- Migrations that fail halfway ---------------------------------------------------

HALFWAY_TABLE = "ROLLBACKPROBE_HALFWAY"


def test_failed_migration_leaves_nothing_behind(live) -> None:
    """An atomic migration that CPA32B2 cancels halfway (a DROP COLUMN in
    RunSQL, where CPA32B2 is not suppressed, after CreateModel, AddField,
    AddIndex and AddConstraint), applied by Django's MigrationExecutor: with
    can_rollback_ddl nothing of it is left, no table, column, index or
    constraint, and no django_migrations row."""
    from django.db import OperationalError, migrations
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.recorder import MigrationRecorder
    from django.db.migrations.state import ProjectState
    from django.db.models import CheckConstraint, Q

    migration = migrations.Migration("0001_halfway", "rollbackprobe")
    migration.operations = [
        migrations.CreateModel(
            "Halfway",
            [
                ("id", models.AutoField(primary_key=True)),
                ("name", models.CharField(max_length=20)),
                ("count", models.IntegerField(default=0)),
            ],
        ),
        migrations.AddField("halfway", "extra", models.CharField(max_length=10, null=True)),
        migrations.AddIndex("halfway", models.Index(fields=["name"], name="rbp_halfway_name_idx")),
        migrations.AddConstraint(
            "halfway", CheckConstraint(condition=Q(count__gte=0), name="rbp_halfway_count_gte_0")
        ),
        # CPA32B2: RunSQL is not a field change, so it is not suppressed.
        migrations.RunSQL(f'ALTER TABLE "{HALFWAY_TABLE}" DROP COLUMN "EXTRA"'),
    ]
    executor = MigrationExecutor(live)
    try:
        with pytest.raises(OperationalError, match="CPA32B2"):
            executor.apply_migration(ProjectState(), migration)
        assert not live.in_atomic_block
        assert _tables(live, HALFWAY_TABLE) == set()
        with live.cursor() as cursor:
            cursor.execute(
                "SELECT INDEX_NAME FROM QSYS2.SYSINDEXES "
                "WHERE INDEX_SCHEMA = CURRENT SCHEMA AND INDEX_NAME = 'RBP_HALFWAY_NAME_IDX'"
            )
            assert cursor.fetchall() == []
            cursor.execute(
                "SELECT CONSTRAINT_NAME FROM QSYS2.SYSCST WHERE CONSTRAINT_SCHEMA = "
                "CURRENT SCHEMA AND CONSTRAINT_NAME = 'RBP_HALFWAY_COUNT_GTE_0'"
            )
            assert cursor.fetchall() == []
        recorded = MigrationRecorder(live).applied_migrations()
        assert ("rollbackprobe", "0001_halfway") not in recorded
    finally:
        replace_if_unusable(live)
        if _tables(live, HALFWAY_TABLE):
            with live.cursor() as cursor:
                cursor.execute(f'DROP TABLE "{HALFWAY_TABLE}"')


def test_failing_deferred_statement_rolls_the_migration_back(live) -> None:
    """A deferred statement that fails (an explicit index on an NCLOB column:
    SQL0350; db_index=True there is skipped) rolls the schema editor's
    transaction back: no table is left, the connection is no longer in an
    atomic block and stays usable. Django's own __exit__ skipped the rollback,
    and the connection was closed later."""
    from django.apps import apps
    from django.db import DatabaseError

    class DeferredProbe(models.Model):
        text = models.TextField()

        class Meta:
            app_label = "testapp"
            indexes = (models.Index(fields=["text"], name="testapp_dp_text_idx"),)

    table = "TESTAPP_DEFERREDPROBE"
    try:
        with pytest.raises(DatabaseError, match="SQL0350"), live.schema_editor() as editor:
            editor.create_model(DeferredProbe)
        assert not live.in_atomic_block
        assert _tables(live, table) == set()
        with live.cursor() as cursor:
            cursor.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
            assert cursor.fetchone() == (1,)
    finally:
        replace_if_unusable(live)
        if _tables(live, table):
            with live.cursor() as cursor:
                cursor.execute(f'DROP TABLE "{table}"')
        apps.all_models["testapp"].pop("deferredprobe", None)
        apps.clear_cache()


# --- AddField of a NOT NULL column without a default ---------------------------------


@pytest.fixture
def not_null_model(live):
    """A model of its own (testapp_addnotnull); created for the test, dropped after."""
    from django.apps import apps

    class AddNotNull(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "testapp"

    try:
        with live.schema_editor() as editor:
            editor.create_model(AddNotNull)
        yield AddNotNull
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute('DROP TABLE "TESTAPP_ADDNOTNULL"')
        apps.all_models["testapp"].pop("addnotnull", None)
        apps.clear_cache()


def _not_null_column(model, name="position"):
    field = models.BigIntegerField()
    field.set_attributes_from_name(name)
    field.model = model
    return field


def _column(live, name: str):
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT IS_NULLABLE, HAS_DEFAULT FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = "
            "CURRENT SCHEMA AND TABLE_NAME = 'TESTAPP_ADDNOTNULL' AND COLUMN_NAME = %s",
            [name],
        )
        row = cursor.fetchone()
    return tuple(value.strip() for value in row) if row else None


def test_not_null_column_without_default_on_an_empty_table(live, not_null_model) -> None:
    """ADD COLUMN ... DEFAULT NOT NULL, then DROP DEFAULT (SQL0109 otherwise):
    the column is NOT NULL without a default, like on PostgreSQL."""
    from django.db import IntegrityError

    with live.schema_editor() as editor:
        editor.add_field(not_null_model, _not_null_column(not_null_model))
    assert _column(live, "POSITION") == ("N", "N")
    with pytest.raises(IntegrityError), live.cursor() as cursor:
        cursor.execute('INSERT INTO "TESTAPP_ADDNOTNULL" ("NAME") VALUES (%s)', ["no position"])


def test_not_null_column_without_default_refused_on_a_table_with_rows(live, not_null_model) -> None:
    """The rows would get the system default: refused, as PostgreSQL refuses
    it; the migration's transaction leaves the table as it was."""
    from django.db import IntegrityError

    not_null_model.objects.create(name="first")
    with (
        pytest.raises(IntegrityError, match="the table has rows"),
        live.schema_editor() as editor,
    ):
        editor.add_field(not_null_model, _not_null_column(not_null_model))
    assert not live.in_atomic_block
    assert _column(live, "POSITION") is None
    assert list(not_null_model.objects.values_list("name", flat=True)) == ["first"]


# --- Check constraints --------------------------------------------------------------


def test_check_constraints_are_enforced(live, empty) -> None:
    """A violated column check or CheckConstraint is SQL0545, with SQLSTATE
    HY000 from the driver, and arrives as IntegrityError (#96)."""
    from django.db import IntegrityError

    author = Author.objects.create(name="Ada")
    rating = Rating.objects.create(stars=5, low=1, high=2, grade="O'")
    violations = [
        lambda: Book.objects.create(author=author, title="Negative", pages=-1),
        lambda: Rating.objects.create(stars=-1),
        lambda: Rating.objects.create(stars=1, low=3, high=2),
        lambda: Rating.objects.create(stars=1, grade="Z"),
        lambda: Rating.objects.filter(pk=rating.pk).update(low=10),
    ]
    for violation in violations:
        with pytest.raises(IntegrityError, match="SQL0545"):
            violation()
    assert list(Rating.objects.values_list("stars", "low", "high", "grade")) == [(5, 1, 2, "O'")]
    assert not Book.objects.exists()


def test_check_constraints_introspected(live) -> None:
    """The CheckConstraints by their names, the column check by Db2's name."""
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, "testapp_rating")
    checks = {name: entry["columns"] for name, entry in constraints.items() if entry["check"]}
    assert checks.pop("testapp_rating_low_lte_high") == ["high", "low"]
    assert checks.pop("testapp_rating_grade") == ["grade"]
    assert list(checks.values()) == [["stars"]]


@pytest.fixture
def check_model(live):
    """A model of its own (testapp_checkprobe) with a PositiveIntegerField;
    created for the test and dropped after it."""
    from django.apps import apps

    class CheckProbe(models.Model):
        count = models.PositiveIntegerField()

        class Meta:
            app_label = "testapp"

    try:
        with live.schema_editor() as editor:
            editor.create_model(CheckProbe)
        yield CheckProbe
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute('DROP TABLE "TESTAPP_CHECKPROBE"')
        apps.all_models["testapp"].pop("checkprobe", None)
        apps.clear_cache()


def _column_checks(live, table: str) -> list[str]:
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, table)
    return sorted(name for name, entry in constraints.items() if entry["check"])


def test_positive_field_to_integer_and_back(live, check_model) -> None:
    """#151: PositiveIntegerField -> IntegerField drops the column check Db2 for
    i named, on a table with rows; the way back adds a named check, once no
    row violates it."""
    from django.db import DatabaseError, IntegrityError

    model = check_model
    model.objects.bulk_create([model(count=0), model(count=5)])
    with pytest.raises(IntegrityError, match="SQL0545"):
        model.objects.create(count=-1)
    [system_name] = _column_checks(live, "testapp_checkprobe")
    assert system_name.startswith("q_")

    positive = _rebuilt(model, "count")
    integer = _rebuilt(model, "count", models.IntegerField)
    with live.schema_editor() as editor:
        editor.alter_field(model, positive, integer, strict=True)
    assert _column_checks(live, "testapp_checkprobe") == []
    model.objects.create(count=-1)
    assert sorted(model.objects.values_list("count", flat=True)) == [-1, 0, 5]

    # The way back while a row has a negative value: SQL0544, nothing changed.
    with pytest.raises(DatabaseError, match="SQL0544"), live.schema_editor() as editor:
        editor.alter_field(model, integer, positive, strict=True)
    assert _column_checks(live, "testapp_checkprobe") == []

    # filter(count=-1) on the PositiveIntegerField would match nothing (Django
    # leaves out values below the field's range), so plain SQL.
    with live.cursor() as cursor:
        cursor.execute('DELETE FROM "TESTAPP_CHECKPROBE" WHERE "COUNT" < 0')
    with live.schema_editor() as editor:
        editor.alter_field(model, integer, positive, strict=True)
    [named] = _column_checks(live, "testapp_checkprobe")
    assert named.startswith("testapp_checkprobe_count_") and named.endswith("_check")
    with pytest.raises(IntegrityError, match="SQL0545"):
        model.objects.create(count=-2)
    assert sorted(model.objects.values_list("count", flat=True)) == [0, 5]


# --- Index column ordering (supports_index_column_ordering) -------------------------


@pytest.fixture
def ranking_model(live):
    """A model of its own (testapp_rankprobe) with a descending index in
    Meta.indexes; created for the test and dropped after it."""
    from django.apps import apps

    class RankProbe(models.Model):
        name = models.CharField(max_length=20)
        score = models.IntegerField()

        class Meta:
            app_label = "testapp"
            indexes = (models.Index(fields=["-score", "name"], name="testapp_rank_score_idx"),)

    try:
        with live.schema_editor() as editor:
            editor.create_model(RankProbe)
        yield RankProbe
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute('DROP TABLE "TESTAPP_RANKPROBE"')
        apps.all_models["testapp"].pop("rankprobe", None)
        apps.clear_cache()


def _orders(live, table: str) -> dict[str, list[str]]:
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, table)
    return {
        name: info["orders"]
        for name, info in constraints.items()
        if info["index"] and not info["primary_key"]
    }


def test_descending_index(live, ranking_model) -> None:
    """Index(fields=["-score", "name"]) is created DESC, ASC and introspected so;
    AddIndex / RemoveIndex with a descending column, and the ORM ordering by it."""
    model = ranking_model
    assert _orders(live, "testapp_rankprobe") == {"testapp_rank_score_idx": ["DESC", "ASC"]}

    added = models.Index(fields=["name", "-score"], name="testapp_rank_name_idx")
    with live.schema_editor() as editor:
        editor.add_index(model, added)
    assert _orders(live, "testapp_rankprobe")["testapp_rank_name_idx"] == ["ASC", "DESC"]
    with live.schema_editor() as editor:
        editor.remove_index(model, added)
    assert "testapp_rank_name_idx" not in _orders(live, "testapp_rankprobe")

    for name, score in (("b", 2), ("a", 3), ("c", 2)):
        model.objects.create(name=name, score=score)
    assert list(model.objects.order_by("-score", "name").values_list("name", flat=True)) == [
        "a",
        "b",
        "c",
    ]


# --- Partial and expression indexes (phase 5, step C) -------------------------------


def _index(live, name):
    with live.cursor() as cursor:
        return live.introspection.get_constraints(cursor, Book._meta.db_table).get(name)


def test_partial_index_used_by_a_migration(live, empty) -> None:
    """AddIndex with a condition: the index exists with its column, queries
    on the table still work, RemoveIndex drops it."""
    index = models.Index(
        fields=["title"], condition=models.Q(pages__gt=100), name="testapp_book_long_idx"
    )
    author = Author.objects.create(name="a")
    Book.objects.create(author=author, title="short", pages=10)
    Book.objects.create(author=author, title="long", pages=500)
    with live.schema_editor() as editor:
        editor.add_index(Book, index)
    try:
        entry = _index(live, index.name)
        assert entry["index"] and entry["columns"] == ["title"] and not entry["unique"]
        titles = Book.objects.filter(pages__gt=100).values_list("title", flat=True)
        assert list(titles) == ["long"]
    finally:
        with live.schema_editor() as editor:
            editor.remove_index(Book, index)
    assert _index(live, index.name) is None


def test_expression_index_has_no_columns(live, empty) -> None:
    """An index on Lower(title) is introspected like Django's other backends
    report it: an index without columns (SYSKEYS.COLUMN_IS_EXPRESSION)."""
    from django.db.models.functions import Lower

    index = models.Index(Lower("title"), name="testapp_book_lower_idx")
    mixed = models.Index("pages", Lower("title"), name="testapp_book_mixed_idx")
    with live.schema_editor() as editor:
        editor.add_index(Book, index)
        editor.add_index(Book, mixed)
    try:
        assert _index(live, index.name)["columns"] == []
        assert _index(live, mixed.name)["columns"] == ["pages", None]
    finally:
        with live.schema_editor() as editor:
            editor.remove_index(Book, index)
            editor.remove_index(Book, mixed)


def test_conditional_unique_constraint(live, empty) -> None:
    """UniqueConstraint(condition=...) is a unique index with WHERE: duplicates
    outside the condition are allowed, inside it they raise IntegrityError."""
    from django.db import IntegrityError, transaction

    constraint = models.UniqueConstraint(
        fields=["title"], condition=models.Q(available=True), name="testapp_book_avail_uniq"
    )
    author = Author.objects.create(name="a")
    with live.schema_editor() as editor:
        editor.add_constraint(Book, constraint)
    try:
        assert _index(live, constraint.name)["unique"]
        Book.objects.create(author=author, title="same", available=False)
        Book.objects.create(author=author, title="same", available=False)
        Book.objects.create(author=author, title="same", available=True)
        with pytest.raises(IntegrityError), transaction.atomic():
            Book.objects.create(author=author, title="same", available=True)
        assert Book.objects.filter(title="same").count() == 3
    finally:
        with live.schema_editor() as editor:
            editor.remove_constraint(Book, constraint)


def test_functional_unique_constraint(live, empty) -> None:
    """UniqueConstraint(Upper("title")): titles that differ only in case clash."""
    from django.db import IntegrityError, transaction
    from django.db.models.functions import Upper

    constraint = models.UniqueConstraint(Upper("title"), name="testapp_book_upper_uniq")
    author = Author.objects.create(name="a")
    with live.schema_editor() as editor:
        editor.add_constraint(Book, constraint)
    try:
        Book.objects.create(author=author, title="Db2 for i")
        with pytest.raises(IntegrityError), transaction.atomic():
            Book.objects.create(author=author, title="DB2 FOR I")
        assert _index(live, constraint.name)["unique"]
    finally:
        with live.schema_editor() as editor:
            editor.remove_constraint(Book, constraint)


# --- Unique constraints and NULLs (phase 5, step D) ----------------------------------


@pytest.fixture
def unique_model(live):
    """A model of its own (testapp_uniquenulls) with nullable unique fields;
    created for the test and dropped after it."""
    from django.apps import apps

    class UniqueNulls(models.Model):
        code = models.CharField(max_length=10, null=True, unique=True)
        a = models.IntegerField(null=True)
        b = models.IntegerField(null=True)
        name = models.CharField(max_length=20, null=True)

        class Meta:
            app_label = "testapp"
            unique_together = (("a", "b"),)

    try:
        with live.schema_editor() as editor:
            editor.create_model(UniqueNulls)
        yield UniqueNulls
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute('DROP TABLE "TESTAPP_UNIQUENULLS"')
        apps.all_models["testapp"].pop("uniquenulls", None)
        apps.clear_cache()


def test_nullable_unique_field_takes_several_nulls(live, unique_model) -> None:
    from django.db import IntegrityError, transaction

    unique_model.objects.create(code=None)
    unique_model.objects.create(code=None)
    unique_model.objects.create(code="x")
    with pytest.raises(IntegrityError), transaction.atomic():
        unique_model.objects.create(code="x")
    assert unique_model.objects.filter(code__isnull=True).count() == 2


def test_partially_nullable_unique_together(live, unique_model) -> None:
    from django.db import IntegrityError, transaction

    unique_model.objects.create(a=1, b=None)
    unique_model.objects.create(a=1, b=None)
    unique_model.objects.create(a=None, b=None)
    unique_model.objects.create(a=None, b=None)
    unique_model.objects.create(a=1, b=2)
    with pytest.raises(IntegrityError), transaction.atomic():
        unique_model.objects.create(a=1, b=2)
    assert unique_model.objects.count() == 5


def test_unique_index_constraints_take_several_nulls(live, unique_model) -> None:
    """A conditional and a functional UniqueConstraint are unique indexes;
    UNIQUE WHERE NOT NULL lets NULLs repeat, duplicates still clash, and
    introspection reports them as unique."""
    from django.db import IntegrityError, transaction
    from django.db.models.functions import Upper

    conditional = models.UniqueConstraint(
        fields=["name"], condition=models.Q(a__gt=0), name="testapp_uniquenulls_name_pos"
    )
    functional = models.UniqueConstraint(Upper("name"), name="testapp_uniquenulls_upper")
    model = unique_model
    with live.schema_editor() as editor:
        editor.add_constraint(model, conditional)
        editor.add_constraint(model, functional)
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, model._meta.db_table)
    assert constraints[conditional.name]["unique"] and constraints[conditional.name]["index"]
    assert constraints[functional.name]["unique"] and constraints[functional.name]["columns"] == []
    model.objects.create(name=None, a=1)
    model.objects.create(name=None, a=2)
    model.objects.create(name="abc", a=3)
    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.create(name="ABC", a=-1)
    assert model.objects.count() == 3
