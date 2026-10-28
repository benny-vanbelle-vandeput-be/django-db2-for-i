"""CPA32B2 suppressed by the schema editor (inquiry.py), against the IBM i.

Each test creates its own table (testapp_narrowing, or the migrations'
cpa32b2probe_shrink) in the test library and drops it again; the module owns
the library's marker (marked_library.py), which also covers the
django_migrations table the migration test needs. The QAQQINI copy
that OVERRIDE_QAQQINI creates lives in QTEMP of this run's own job. Never more
than one connection at a time: the option test closes the default connection
before it opens its own.

The narrowing cases measure as Db2 for i does (probe qaqqini_lifecycle):
NVARCHAR in UTF-16 code units (an emoji counts 2), VARCHAR CCSID 1208 in
bytes, and a number fails on any value that would change.
"""

from decimal import Decimal

import pytest
from django.db import DataError, IntegrityError, OperationalError, models

from django_db2_for_i.base import DatabaseWrapper
from tests.ibmi.connection_guard import replace_if_unusable
from tests.ibmi.marked_library import marked_library

TABLE = "TESTAPP_NARROWING"
QAQQINI_COPY = "SELECT COUNT(*) FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE', 'QAQQINI')) X"
COLUMN = (
    "SELECT DATA_TYPE, LENGTH, NUMERIC_SCALE, IS_NULLABLE FROM QSYS2.SYSCOLUMNS "
    "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s AND COLUMN_NAME = %s"
)


@pytest.fixture(scope="module", autouse=True)
def marked_empty_library(django_db_blocker, request):
    with django_db_blocker.unblock(), marked_library(request.node.nodeid):
        yield


class Utf8CharField(models.CharField):
    """VARCHAR(n) CCSID 1208: its length counts UTF-8 bytes."""

    def db_type(self, connection):
        return f"VARCHAR({self.max_length}) CCSID 1208"


@pytest.fixture
def narrowing(live):
    """A model of its own, created for the test and dropped after it."""
    from django.apps import apps

    class Narrowing(models.Model):
        text = models.CharField(max_length=10, null=True)
        utf8 = Utf8CharField(max_length=10, null=True)
        note = models.TextField(null=True)
        amount = models.DecimalField(max_digits=9, decimal_places=4, null=True)
        number = models.IntegerField(null=True)
        ratio = models.FloatField(null=True)

        class Meta:
            app_label = "testapp"

    try:
        with live.schema_editor() as editor:
            editor.create_model(Narrowing)
        yield Narrowing
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute(f'DROP TABLE "{TABLE}"')
        apps.all_models["testapp"].pop("narrowing", None)
        apps.clear_cache()


def _field(model, name, cls=None, **changes):
    """``model``'s field rebuilt with ``changes``, as a migration's AlterField has it."""
    old = model._meta.get_field(name)
    _name, _path, args, kwargs = old.deconstruct()
    field = (cls or type(old))(*args, **{**kwargs, **changes})
    field.set_attributes_from_name(name)
    field.model = model
    return field


def _column(wrapper, name: str, table: str = TABLE):
    with wrapper.cursor() as cursor:
        cursor.execute(COLUMN, [table, name.upper()])
        row = cursor.fetchone()
    return tuple(v.strip() if isinstance(v, str) else v for v in row) if row else None


def _copy_exists(wrapper) -> bool:
    with wrapper.cursor() as cursor:
        cursor.execute(QAQQINI_COPY)
        return cursor.fetchone()[0] > 0


def _assert_suppression_ended(wrapper) -> None:
    assert not wrapper._inquiry_override_pending
    assert not wrapper._inquiry_suppressed
    assert not _copy_exists(wrapper)


EMOJI = "\U0001f600"
CASES = [
    # NVARCHAR(10) -> NVARCHAR(5): UTF-16 code units, an emoji counts 2.
    ("text", None, {"max_length": 5}, "abcde", False),
    ("text", None, {"max_length": 5}, "abcdef", True),
    ("text", None, {"max_length": 5}, f"abc{EMOJI}", False),
    ("text", None, {"max_length": 5}, f"abcd{EMOJI}", True),
    # VARCHAR(10) CCSID 1208 -> VARCHAR(5) CCSID 1208: bytes (é 2, an emoji 4).
    ("utf8", None, {"max_length": 5}, "abcde", False),
    ("utf8", None, {"max_length": 5}, "abcé", False),
    ("utf8", None, {"max_length": 5}, "abcdé", True),
    ("utf8", None, {"max_length": 5}, f"a{EMOJI}", False),
    ("utf8", None, {"max_length": 5}, f"ab{EMOJI}", True),
    # NCLOB (TextField) -> NVARCHAR(5) (CharField).
    ("note", models.CharField, {"max_length": 5}, f"abc{EMOJI}", False),
    ("note", models.CharField, {"max_length": 5}, f"abcd{EMOJI}", True),
    # DECIMAL(9, 4) -> fewer decimals: any digit lost counts (Db2 truncates).
    ("amount", None, {"decimal_places": 2}, Decimal("1.2300"), False),
    ("amount", None, {"decimal_places": 2}, Decimal("1.2345"), True),
    ("amount", None, {"decimal_places": 2}, Decimal("-1.2301"), True),
    # DECIMAL(9, 4) -> DECIMAL(4, 2): fewer integer digits.
    ("amount", None, {"max_digits": 4, "decimal_places": 2}, Decimal("99.99"), False),
    ("amount", None, {"max_digits": 4, "decimal_places": 2}, Decimal("100.00"), True),
    # INTEGER -> SMALLINT.
    ("number", models.SmallIntegerField, {}, 32767, False),
    ("number", models.SmallIntegerField, {}, 32768, True),
    # DOUBLE -> DECIMAL(5, 2): the double nearest 0.29 would become 0.28.
    ("ratio", models.DecimalField, {"max_digits": 5, "decimal_places": 2}, 0.5, False),
    ("ratio", models.DecimalField, {"max_digits": 5, "decimal_places": 2}, 0.29, True),
]


@pytest.mark.parametrize(("name", "cls", "changes", "value", "refused"), CASES)
def test_narrowing(live, narrowing, name, cls, changes, value, refused) -> None:
    """A value that fits: the column changes and the value stays. A value that
    would be truncated or rounded: DataError, and the column is unchanged."""
    old, new = _field(narrowing, name), _field(narrowing, name, cls, **changes)
    narrowing.objects.create(**{name: value})
    before = _column(live, name)
    if refused:
        with (
            pytest.raises(DataError, match="would truncate or round"),
            live.schema_editor() as editor,
        ):
            editor.alter_field(narrowing, old, new, strict=True)
        assert _column(live, name) == before
    else:
        with live.schema_editor() as editor:
            editor.alter_field(narrowing, old, new, strict=True)
        assert _column(live, name) != before
        with live.cursor() as cursor:
            cursor.execute(f'SELECT "{name.upper()}" FROM "{TABLE}"')
            assert cursor.fetchone()[0] == value
    _assert_suppression_ended(live)


def test_remove_field_from_a_table_with_rows(live, narrowing) -> None:
    """DROP COLUMN goes through; the suppression lasts until the schema editor
    exits, and outside a field change CPA32B2 is a safety net again."""
    narrowing.objects.create(text="x", number=1)
    with live.schema_editor() as editor:
        editor.remove_field(narrowing, narrowing._meta.get_field("number"))
        assert live._inquiry_suppressed
        assert _copy_exists(live)
    assert _column(live, "number") is None
    _assert_suppression_ended(live)
    with (
        pytest.raises(OperationalError, match="ran outside them"),
        live.schema_editor() as editor,
    ):
        editor.execute(f'ALTER TABLE "{TABLE}" DROP COLUMN "RATIO"')
    assert _column(live, "ratio") is not None


def test_set_not_null(live, narrowing) -> None:
    """SET NOT NULL goes through without NULLs; with a NULL Db2 for i refuses
    it itself (SQL0407), also with CPA32B2 suppressed."""
    narrowing.objects.create(text="x", number=1)
    nullable, not_null = _field(narrowing, "text"), _field(narrowing, "text", null=False)
    with live.schema_editor() as editor:
        editor.alter_field(narrowing, nullable, not_null, strict=True)
    assert _column(live, "text")[3] == "N"
    narrowing.objects.create(text="y", number=None)
    nullable, not_null = _field(narrowing, "number"), _field(narrowing, "number", null=False)
    with pytest.raises(IntegrityError, match="SQL0407"), live.schema_editor() as editor:
        editor.alter_field(narrowing, nullable, not_null, strict=True)
    assert _column(live, "number")[3] == "Y"
    _assert_suppression_ended(live)


def test_without_a_transaction(live, narrowing) -> None:
    """atomic = False: the same in autocommit, refused and allowed."""
    narrowing.objects.create(text="abcdef")
    old = _field(narrowing, "text")
    with pytest.raises(DataError), live.schema_editor(atomic=False) as editor:
        editor.alter_field(narrowing, old, _field(narrowing, "text", max_length=5))
    _assert_suppression_ended(live)
    with live.schema_editor(atomic=False) as editor:
        editor.alter_field(narrowing, old, _field(narrowing, "text", max_length=6))
        assert not live.in_atomic_block
    assert _column(live, "text")[1] == 6
    _assert_suppression_ended(live)


def test_nested_editors_end_with_the_outermost(live, narrowing) -> None:
    """The inner schema editor leaves the suppression on; the outermost ends it."""
    with live.schema_editor():
        with live.schema_editor() as inner:
            inner.alter_field(
                narrowing, _field(narrowing, "text"), _field(narrowing, "text", max_length=5)
            )
        assert live._inquiry_suppressed
        assert _copy_exists(live)
    _assert_suppression_ended(live)
    assert _column(live, "text")[1] == 5


SHRINK_TABLE = "CPA32B2PROBE_SHRINK"


def test_migrations_narrow_and_remove_and_back(live) -> None:
    """Migrations applied by Django's MigrationExecutor (atomic): the first
    creates the table and adds a row, the second narrows a column and drops
    one; then both are unapplied again. Two migrations, since Db2 for i
    refuses an ALTER TABLE on a table created and changed in the same
    transaction (SQL0910)."""
    from django.db import migrations
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.recorder import MigrationRecorder
    from django.db.migrations.state import ProjectState

    def add_row(apps, schema_editor):
        apps.get_model("cpa32b2probe", "Shrink").objects.create(name="abc", extra=1)

    create = migrations.Migration("0001_create", "cpa32b2probe")
    create.operations = [
        migrations.CreateModel(
            "Shrink",
            [
                ("id", models.AutoField(primary_key=True)),
                ("name", models.CharField(max_length=20)),
                ("extra", models.IntegerField(null=True)),
            ],
        ),
        migrations.RunPython(add_row, migrations.RunPython.noop),
    ]
    shrink = migrations.Migration("0002_shrink", "cpa32b2probe")
    shrink.operations = [
        migrations.AlterField("shrink", "name", models.CharField(max_length=10)),
        migrations.RemoveField("shrink", "extra"),
    ]
    executor = MigrationExecutor(live)
    try:
        created = executor.apply_migration(ProjectState(), create)
        executor.apply_migration(created.clone(), shrink)
        assert _column(live, "name", SHRINK_TABLE) == ("VARG", 10, None, "N")
        assert _column(live, "extra", SHRINK_TABLE) is None
        _assert_suppression_ended(live)
        with live.cursor() as cursor:
            cursor.execute(f'SELECT "NAME" FROM "{SHRINK_TABLE}"')
            assert cursor.fetchall() == [("abc",)]
        executor.unapply_migration(created.clone(), shrink)
        assert _column(live, "name", SHRINK_TABLE) == ("VARG", 20, None, "N")
        assert _column(live, "extra", SHRINK_TABLE) is not None
        _assert_suppression_ended(live)
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM QSYS2.SYSTABLES "
                "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s",
                [SHRINK_TABLE],
            )
            if cursor.fetchone()[0]:
                cursor.execute(f'DROP TABLE "{SHRINK_TABLE}"')
        recorder = MigrationRecorder(live)
        for name in ("0001_create", "0002_shrink"):
            recorder.record_unapplied("cpa32b2probe", name)


def test_option_off_keeps_cpa32b2(live, narrowing) -> None:
    """OPTIONS['suppress_inquiry_messages'] = False: DROP COLUMN in a field
    change is cancelled by CPA32B2 again, and the error names the option.
    atomic=False: an atomic block needs a connection in django.db.connections."""
    live.close()  # one connection at a time
    settings_dict = {
        **live.settings_dict,
        "OPTIONS": {**live.settings_dict["OPTIONS"], "suppress_inquiry_messages": False},
    }
    wrapper = DatabaseWrapper(settings_dict, alias="cpa32b2_off")
    try:
        with (
            pytest.raises(OperationalError, match="is False for this database"),
            wrapper.schema_editor(atomic=False) as editor,
        ):
            editor.remove_field(narrowing, narrowing._meta.get_field("number"))
        assert not _copy_exists(wrapper)
        assert _column(wrapper, "number") is not None
    finally:
        wrapper.close()
