"""Tables in another library than NAME on a real Db2 for i (#124; probes
lib_other_library, qtemp_qualified_names).

The models live in the ``other`` library of ``.env`` (``DB2I_OTHER_LIBRARY``), through
the ``default`` connection, whose current schema stays ``NAME``. The ``other`` library
is marked for the module like the default one (DJDB2I_TEST_MARKER, the creation safety
gate) and left without tables, marker included; every table is on the cleanup list
(tests/table_registry.py records the library of ``CREATE TABLE "LIB"."T"``).
"""

import contextlib
import os

import pytest
from django.db import IntegrityError, models, transaction

from tests.ibmi.connection_guard import replace_if_unusable
from tests.ibmi.marked_library import unmarked_creates_allowed

pytestmark = pytest.mark.usefixtures("testapp_tables")

OTHER = os.environ.get("DB2I_OTHER_LIBRARY", "").strip().upper()


@contextlib.contextmanager
def _marked_other_library(live):
    """The creation safety gate for the other library, on the default connection."""
    test = live.settings_dict["TEST"]
    saved = test["NAME"]
    test["NAME"] = OTHER
    try:
        with unmarked_creates_allowed():
            live.creation._create_test_db(verbosity=0, autoclobber=True, keepdb=False)
    finally:
        test["NAME"] = saved
    try:
        yield
    finally:
        replace_if_unusable(live)
        live.creation._destroy_test_db(OTHER, 0)


@pytest.fixture
def other_models(live):
    """A parent and an order table in the other library, with a foreign key, unique
    and check constraints, a plain and a conditional unique index; and a model that
    names the library with Meta.db_library."""
    if not OTHER:
        pytest.skip("DB2I_OTHER_LIBRARY is not set")
    from django.apps import apps

    class OtherParent(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "testapp"
            db_table = f'{OTHER}"."testapp_ol_parent'

    class OtherOrder(models.Model):
        parent = models.ForeignKey(OtherParent, models.CASCADE)
        number = models.IntegerField()
        code = models.CharField(max_length=10)

        class Meta:
            app_label = "testapp"
            db_table = f'{OTHER}"."testapp_ol_order'
            constraints = (
                models.UniqueConstraint(fields=["number"], name="testapp_ol_number_uniq"),
                models.CheckConstraint(
                    condition=models.Q(number__gt=0), name="testapp_ol_number_positive"
                ),
                models.UniqueConstraint(
                    fields=["code"], condition=models.Q(number__gt=100), name="testapp_ol_code_uniq"
                ),
            )
            indexes = (models.Index(fields=["code"], name="testapp_ol_code_idx"),)

    class OtherNote(models.Model):
        text = models.CharField(max_length=20)

        class Meta:
            app_label = "testapp"
            db_table = "testapp_ol_note"
            db_library = OTHER

    created = []
    with _marked_other_library(live):
        try:
            with live.schema_editor() as editor:
                for model in (OtherParent, OtherOrder, OtherNote):
                    editor.create_model(model)
                    created.append(model)
            yield OtherParent, OtherOrder, OtherNote
        finally:
            replace_if_unusable(live)
            with live.schema_editor() as editor:
                for model in reversed(created):
                    editor.delete_model(model)
            for name in ("otherparent", "otherorder", "othernote"):
                apps.all_models["testapp"].pop(name, None)
            apps.clear_cache()


def _catalog(live, sql: str) -> list[str]:
    with live.cursor() as cursor:
        cursor.execute(sql, [OTHER])
        return sorted(row[0].rstrip() for row in cursor.fetchall())


def test_constraints_and_indexes_are_in_the_other_library(live, other_models) -> None:
    constraints = _catalog(
        live,
        "SELECT CONSTRAINT_NAME FROM QSYS2.SYSCST WHERE TABLE_SCHEMA = %s "
        "AND TABLE_NAME = 'TESTAPP_OL_ORDER' AND CONSTRAINT_SCHEMA = TABLE_SCHEMA",
    )
    assert {"TESTAPP_OL_NUMBER_UNIQ", "TESTAPP_OL_NUMBER_POSITIVE"} <= set(constraints)
    assert any("_FK_" in name for name in constraints)  # Django's foreign key name
    indexes = _catalog(
        live,
        "SELECT INDEX_NAME FROM QSYS2.SYSINDEXES WHERE TABLE_SCHEMA = %s "
        "AND TABLE_NAME = 'TESTAPP_OL_ORDER' AND INDEX_SCHEMA = TABLE_SCHEMA",
    )
    assert {"TESTAPP_OL_CODE_IDX", "TESTAPP_OL_CODE_UNIQ"} <= set(indexes)
    # Nothing of these tables landed in NAME.
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM QSYS2.SYSINDEXES WHERE INDEX_SCHEMA = CURRENT SCHEMA "
            "AND TABLE_SCHEMA = %s",
            [OTHER],
        )
        assert cursor.fetchone()[0] == 0


def test_introspection_reads_the_other_library(live, other_models) -> None:
    _parent, order, note = other_models
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, order._meta.db_table)
        description = live.introspection.get_table_description(cursor, note._meta.db_table)
    columns = [column.name for column in description]
    assert constraints["testapp_ol_number_uniq"]["unique"]
    assert constraints["testapp_ol_number_positive"]["check"]
    assert constraints["testapp_ol_code_idx"]["index"]
    foreign_keys = [c for c in constraints.values() if c["foreign_key"]]
    assert [fk["foreign_key"] for fk in foreign_keys] == [("testapp_ol_parent", "id")]
    assert columns == ["id", "text"]


def test_the_orm_and_the_constraints_work(live, other_models) -> None:
    parent_model, order_model, note_model = other_models
    parent = parent_model.objects.create(name="p")
    order_model.objects.create(parent=parent, number=1, code="a")
    note_model.objects.create(text="hello")
    assert order_model.objects.select_related("parent").get(number=1).parent.name == "p"
    assert note_model.objects.get().text == "hello"
    for bad in (
        {"parent": parent, "number": 1, "code": "b"},  # unique
        {"parent": parent, "number": -1, "code": "c"},  # check
        {"parent_id": parent.pk + 100, "number": 2, "code": "d"},  # foreign key
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            order_model.objects.create(**bad)
    parent.delete()  # Django's CASCADE
    assert order_model.objects.count() == 0


def test_schema_changes_on_the_other_library(live, other_models) -> None:
    _parent, order, _note = other_models
    index = models.Index(fields=["number"], name="testapp_ol_number_idx")
    renamed = models.Index(fields=["number"], name="testapp_ol_number_ix2")
    check = models.CheckConstraint(condition=models.Q(number__lt=1000), name="testapp_ol_below")
    with live.schema_editor() as editor:
        editor.add_index(order, index)
        editor.rename_index(order, index, renamed)
        editor.add_constraint(order, check)
    with live.cursor() as cursor:
        names = live.introspection.get_constraints(cursor, order._meta.db_table)
    assert "testapp_ol_number_ix2" in names
    assert "testapp_ol_below" in names
    with live.schema_editor() as editor:
        editor.remove_constraint(order, check)
        editor.remove_index(order, renamed)
        old, new = order._meta.db_table, f'{OTHER}"."testapp_ol_order_2'
        editor.alter_db_table(order, old, new)
        editor.alter_db_table(order, new, old)
    with live.cursor() as cursor:
        names = live.introspection.get_constraints(cursor, order._meta.db_table)
    assert "testapp_ol_number_ix2" not in names
    assert "testapp_ol_below" not in names
