"""IBM i system names of columns: the field mixin, the DDL, the checks (#253)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, models
from django.test.utils import isolate_apps

from django_db2_for_i import validation
from django_db2_for_i.fields import SystemNameMixin, normalize_system_name, with_system_name
from tests.testapp.models import Author

pytestmark = pytest.mark.offline

SystemNameCharField = with_system_name(models.CharField, __name__)
SystemNameIntegerField = with_system_name(models.IntegerField, __name__)


class OwnMixinField(models.CharField):
    """A project's own mixin: only the attribute counts."""

    def __init__(self, *args, db_system_name="", **kwargs):
        self.db_system_name = db_system_name
        super().__init__(*args, **kwargs)


@pytest.mark.parametrize(("name", "expected"), [("dlvaddr", "DLVADDR"), (" A_1 ", "A_1")])
def test_names_are_uppercased(name, expected) -> None:
    assert normalize_system_name(name) == expected


@pytest.mark.parametrize("name", ["ELEVENCHARS", "1ABC", "PSN#@$", '"quoted"', "A B", ""])
def test_invalid_names_are_refused(name) -> None:
    with pytest.raises(ImproperlyConfigured, match="not a valid IBM i system name"):
        normalize_system_name(name)


def test_the_mixin_keeps_the_name_in_migrations() -> None:
    field = SystemNameCharField(max_length=10, db_system_name="dlvaddr")
    assert field.db_system_name == "DLVADDR"
    _name, path, _args, kwargs = field.deconstruct()
    assert path == f"{__name__}.SystemNameCharField"
    assert kwargs["db_system_name"] == "DLVADDR"
    assert "db_system_name" not in SystemNameCharField(max_length=10).deconstruct()[3]


def test_the_mixin_refuses_an_invalid_name() -> None:
    with pytest.raises(ImproperlyConfigured):
        SystemNameCharField(max_length=10, db_system_name="TOO_LONG_NAME")


def test_a_class_with_the_mixin() -> None:
    class AddressField(SystemNameMixin, models.CharField):
        pass

    assert AddressField(max_length=5, db_system_name="ADDR").db_system_name == "ADDR"


def _column_ddl(field, name) -> str:
    field.set_attributes_from_name(name)
    field.model = Author
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        definition, _params = editor.column_sql(Author, field)
    return definition


def test_a_long_column_gets_for_column() -> None:
    field = SystemNameCharField(max_length=100, db_system_name="DLVADDR")
    assert _column_ddl(field, "delivery_address") == "FOR COLUMN DLVADDR NVARCHAR(100) NOT NULL"


def test_a_short_column_may_get_another_system_name() -> None:
    field = SystemNameIntegerField(db_system_name="QTY", null=True)
    assert _column_ddl(field, "amount") == "FOR COLUMN QTY INTEGER"


def test_a_column_named_as_its_system_name_gets_no_clause() -> None:
    field = SystemNameIntegerField(db_system_name="amount", null=True)
    assert _column_ddl(field, "amount") == "INTEGER"


def test_a_plain_field_gets_no_clause() -> None:
    assert _column_ddl(models.IntegerField(null=True), "a_long_column_name") == "INTEGER"


def test_a_projects_own_mixin_works_too() -> None:
    field = OwnMixinField(max_length=5, db_system_name="own")
    assert _column_ddl(field, "own_long_name") == "FOR COLUMN OWN NVARCHAR(5) NOT NULL"


@isolate_apps("tests.testapp")
def test_create_table_writes_the_system_names() -> None:
    class Customer(models.Model):
        delivery_address = SystemNameCharField(max_length=100, db_system_name="DLVADDR")
        city = models.CharField(max_length=50)

        class Meta:
            app_label = "testapp"

    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.create_model(Customer)
    create = editor.collected_sql[0]
    assert '"DELIVERY_ADDRESS" FOR COLUMN DLVADDR NVARCHAR(100) NOT NULL' in create
    assert '"CITY" NVARCHAR(50) NOT NULL' in create


@isolate_apps("tests.testapp")
def test_the_checks() -> None:
    class Order(models.Model):
        quantity = SystemNameIntegerField(db_system_name="QTY")
        qty = models.IntegerField()  # a short name is its own system name
        total = SystemNameIntegerField(db_system_name="QTY")
        bad = OwnMixinField(max_length=5, db_system_name="1BAD")

        class Meta:
            app_label = "testapp"

    fields = {f.name: f for f in Order._meta.local_fields}
    assert validation.check_system_name(fields["quantity"]) == []
    (clash,) = validation.check_system_name(fields["qty"])
    assert clash.id == validation.E002
    assert "'quantity'" in clash.msg
    (again,) = validation.check_system_name(fields["total"])
    assert again.id == validation.E002
    (invalid,) = validation.check_system_name(fields["bad"])
    assert invalid.id == validation.E001


def test_changing_the_system_name_alters_nothing() -> None:
    """AlterField of only db_system_name: Db2 for i cannot rename a column, and
    the backend writes no statement for it."""
    old = SystemNameIntegerField(db_system_name="QTY", null=True)
    new = SystemNameIntegerField(db_system_name="QUANTITY", null=True)
    for field in (old, new):
        field.set_attributes_from_name("amount_long_name")
        field.model = Author
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.alter_field(Author, old, new)
    assert editor.collected_sql == []
