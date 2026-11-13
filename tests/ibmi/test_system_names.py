"""IBM i system names of columns, tables and indexes on a real Db2 for i (#253; probe
qtemp_system_names).

A model of its own (testapp_sysnames), created for the test and dropped after.
"""

import pytest
from django.db import models

from django_db2_for_i.fields import with_system_name
from django_db2_for_i.indexes import SystemNameIndex
from tests.ibmi.connection_guard import replace_if_unusable

pytestmark = pytest.mark.usefixtures("testapp_tables")

SystemNameCharField = with_system_name(models.CharField, __name__)
SystemNameIntegerField = with_system_name(models.IntegerField, __name__)

TABLE = "TESTAPP_SYSNAMES"


@pytest.fixture
def sysnames_model(live):
    from django.apps import apps

    class SysNames(models.Model):
        delivery_address = SystemNameCharField(max_length=100, db_system_name="DLVADDR")
        amount = SystemNameIntegerField(db_system_name="QTY", default=0)
        a_long_plain_column = models.IntegerField(default=0)

        class Meta:
            app_label = "testapp"

    try:
        with live.schema_editor() as editor:
            editor.create_model(SysNames)
        yield SysNames
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute(f'DROP TABLE "{TABLE}"')
        apps.all_models["testapp"].pop("sysnames", None)
        apps.clear_cache()


def _system_names(live) -> dict[str, str]:
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME, SYSTEM_COLUMN_NAME FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s",
            [TABLE],
        )
        return {name: system.strip() for name, system in cursor.fetchall()}


def test_create_table_sets_the_system_names(live, sysnames_model) -> None:
    names = _system_names(live)
    assert names["DELIVERY_ADDRESS"] == "DLVADDR"
    assert names["AMOUNT"] == "QTY"
    # A plain field: IBM i derives the system name, as before.
    assert names["A_LONG_PLAIN_COLUMN"] != "A_LONG_PLAIN_COLUMN"
    assert len(names["A_LONG_PLAIN_COLUMN"]) <= 10


def test_the_model_reads_and_writes_through_the_sql_names(live, sysnames_model) -> None:
    sysnames_model.objects.create(delivery_address="Main Street 1", amount=3)
    row = sysnames_model.objects.get()
    assert (row.delivery_address, row.amount) == ("Main Street 1", 3)
    with live.cursor() as cursor:  # the same row through the system names
        cursor.execute(f'SELECT DLVADDR, QTY FROM "{TABLE}"')
        assert cursor.fetchall() == [("Main Street 1", 3)]


def test_add_column_sets_the_system_name(live, sysnames_model) -> None:
    field = SystemNameIntegerField(db_system_name="ADDEDCOL", null=True)
    field.set_attributes_from_name("added_long_column")
    field.model = sysnames_model
    with live.schema_editor() as editor:
        editor.add_field(sysnames_model, field)
    assert _system_names(live)["ADDED_LONG_COLUMN"] == "ADDEDCOL"


ORDERS = "TESTAPP_SYSNAME_ORDERS"


@pytest.fixture
def orders_model(live):
    """A table and an index with system names, rendered through the migration state
    (as migrate creates it), plus a unique constraint and a plain index."""
    from django.apps import apps
    from django.db.migrations.state import ModelState, StateApps

    class SysNameOrders(models.Model):
        number = models.CharField(max_length=20)
        customer = models.CharField(max_length=50)

        class Meta:
            app_label = "testapp"
            db_table = "testapp_sysname_orders"
            db_system_name = "SYSORD"
            indexes = (
                SystemNameIndex(
                    fields=["customer"], name="testapp_sysord_customer", db_system_name="SYSORDCU"
                ),
                models.Index(fields=["number", "customer"], name="testapp_sysord_plain"),
            )
            constraints = (
                models.UniqueConstraint(fields=["number"], name="testapp_sysord_number_uniq"),
            )

    state = ModelState.from_model(SysNameOrders)
    assert state.options["db_system_name"] == "SYSORD"
    rendered = state.render(StateApps([], {}))
    try:
        with live.schema_editor() as editor:
            editor.create_model(rendered)
        yield SysNameOrders
    finally:
        replace_if_unusable(live)
        with live.cursor() as cursor:
            cursor.execute(f'DROP TABLE "{ORDERS}"')
        apps.all_models["testapp"].pop("sysnameorders", None)
        apps.clear_cache()


def test_table_and_index_get_their_system_names(live, orders_model) -> None:
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s",
            [ORDERS],
        )
        assert [row[0].strip() for row in cursor.fetchall()] == ["SYSORD"]
        cursor.execute(
            "SELECT INDEX_NAME, SYSTEM_INDEX_NAME FROM QSYS2.SYSINDEXES "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s ORDER BY INDEX_NAME",
            [ORDERS],
        )
        indexes = {name: system.strip() for name, system in cursor.fetchall()}
    assert indexes["TESTAPP_SYSORD_CUSTOMER"] == "SYSORDCU"
    # The plain index: IBM i makes the system name up, as before.
    assert indexes["TESTAPP_SYSORD_PLAIN"] not in ("SYSORDCU", "TESTAPP_SY")
    assert len(indexes["TESTAPP_SYSORD_PLAIN"]) <= 10


def test_a_unique_constraint_is_no_file_object(live, orders_model) -> None:
    """Only tables and indexes are *FILE objects, so only they need a system name."""
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT OBJLONGNAME, OBJATTRIBUTE FROM TABLE(QSYS2.OBJECT_STATISTICS("
            "CURRENT SCHEMA, '*FILE')) X WHERE OBJLONGNAME LIKE 'TESTAPP_SYS%%' "
            "ORDER BY OBJLONGNAME"
        )
        objects = [(name.strip(), attribute.strip()) for name, attribute in cursor.fetchall()]
    assert ("TESTAPP_SYSNAME_ORDERS", "PF") in objects
    assert ("TESTAPP_SYSORD_CUSTOMER", "LF") in objects
    assert not any("UNIQ" in name for name, _attribute in objects)


def test_the_model_reads_and_writes_through_the_sql_names_of_the_table(live, orders_model) -> None:
    orders_model.objects.create(number="A-1", customer="Acme")
    assert orders_model.objects.get(customer="Acme").number == "A-1"
    with live.cursor() as cursor:  # the same row through the system name
        cursor.execute("SELECT NUMBER FROM SYSORD")
        assert cursor.fetchall() == [("A-1",)]
