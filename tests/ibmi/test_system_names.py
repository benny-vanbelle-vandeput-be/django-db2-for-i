"""IBM i system names of columns on a real Db2 for i (#253; probe qtemp_system_names).

A model of its own (testapp_sysnames), created for the test and dropped after.
"""

import pytest
from django.db import models

from django_db2_for_i.fields import with_system_name
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
