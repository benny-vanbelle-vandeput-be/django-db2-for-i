"""IBM i system names of columns: the field mixin, the DDL, the checks (#253)."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, models
from django.test.utils import isolate_apps

from django_db2_for_i import validation
from django_db2_for_i.fields import SystemNameMixin, normalize_system_name, with_system_name
from django_db2_for_i.indexes import SystemNameIndex
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


# --- Tables (Meta.db_system_name, apps.py) and indexes (indexes.py) ---------------


def test_meta_db_system_name_is_an_accepted_option() -> None:
    from django.db.migrations import state
    from django.db.models import options

    assert "db_system_name" in options.DEFAULT_NAMES
    assert "db_system_name" in state.DEFAULT_NAMES


@isolate_apps("tests.testapp")
def test_create_table_writes_the_table_system_name() -> None:
    class CustomerAddress(models.Model):
        city = models.CharField(max_length=50)

        class Meta:
            app_label = "testapp"
            db_table = "customer_addresses"
            db_system_name = "custaddr"

    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.create_model(CustomerAddress)
    assert editor.collected_sql[0].startswith(
        'CREATE TABLE "CUSTOMER_ADDRESSES" FOR SYSTEM NAME CUSTADDR ("ID" '
    )


@isolate_apps("tests.testapp")
def test_migrations_keep_the_table_system_name() -> None:
    from django.db.migrations.state import ModelState

    class Invoice(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "invoice_headers"
            db_system_name = "INVHDR"

    model_state = ModelState.from_model(Invoice)
    assert model_state.options["db_system_name"] == "INVHDR"
    rendered = model_state.render(Invoice._meta.apps.__class__())
    assert rendered._meta.db_system_name == "INVHDR"


@isolate_apps("tests.testapp")
def test_a_short_table_name_refuses_another_system_name() -> None:
    class Short(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "shorttab"
            db_system_name = "OTHER"

    with (
        pytest.raises(ImproperlyConfigured, match="SQL7029"),
        connection.schema_editor(collect_sql=True, atomic=False) as editor,
    ):
        editor.create_model(Short)


@isolate_apps("tests.testapp")
def test_a_table_without_one_is_unchanged() -> None:
    class Plain(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "plain_long_table_name"

    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.create_model(Plain)
    assert editor.collected_sql[0].startswith('CREATE TABLE "PLAIN_LONG_TABLE_NAME" ("ID" ')


def test_the_index_keeps_its_system_name_in_migrations() -> None:
    index = SystemNameIndex(fields=["name"], name="author_name_idx", db_system_name="authnm")
    path, _args, kwargs = index.deconstruct()
    assert path == "django_db2_for_i.indexes.SystemNameIndex"
    assert kwargs["db_system_name"] == "AUTHNM"
    assert index.clone().db_system_name == "AUTHNM"
    plain = SystemNameIndex(fields=["name"], name="author_name_idx")
    assert "db_system_name" not in plain.deconstruct()[2]


def test_add_index_writes_the_index_system_name() -> None:
    index = SystemNameIndex(fields=["name"], name="author_name_idx", db_system_name="AUTHNM")
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.add_index(Author, index)
    assert editor.collected_sql == [
        'CREATE INDEX "AUTHOR_NAME_IDX" FOR SYSTEM NAME AUTHNM ON "TESTAPP_AUTHOR" ("NAME");'
    ]


def test_a_projects_own_index_with_the_attribute_works_too() -> None:
    index = models.Index(fields=["name"], name="author_name_own")
    index.db_system_name = "AUTHOWN"
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.add_index(Author, index)
    assert "FOR SYSTEM NAME AUTHOWN ON" in editor.collected_sql[0]


@isolate_apps("tests.testapp")
def test_create_model_writes_the_meta_index_system_names() -> None:
    class Customer(models.Model):
        city = models.CharField(max_length=50)
        zip_code = models.CharField(max_length=10, db_index=True)

        class Meta:
            app_label = "testapp"
            indexes = (
                SystemNameIndex(
                    fields=["city"], name="customer_city_idx", db_system_name="CUSTCITY"
                ),
                models.Index(fields=["city", "zip_code"], name="customer_city_zip"),
            )

    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.create_model(Customer)
    indexes = [sql for sql in editor.collected_sql if sql.startswith("CREATE INDEX")]
    assert 'CREATE INDEX "CUSTOMER_CITY_IDX" FOR SYSTEM NAME CUSTCITY ON' in "\n".join(indexes)
    others = [sql for sql in indexes if "CUSTOMER_CITY_IDX" not in sql]
    assert len(others) == 2  # the plain Meta index and the db_index one
    assert not any("FOR SYSTEM NAME" in sql for sql in others)


@isolate_apps("tests.testapp")
def test_the_table_and_index_checks() -> None:
    class Order(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "order_headers"
            db_system_name = "ORDHDR"
            indexes = (
                SystemNameIndex(fields=["id"], name="order_id_index", db_system_name="ORDHDR"),
                SystemNameIndex(fields=["id"], name="shortidx", db_system_name="OTHER"),
            )

    class OrderLine(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "ordhdr"  # a short name is its own system name

    class Bad(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "bad_long_table_name"
            db_system_name = "1BAD"

    issues = validation.check_object_system_names([Order, OrderLine, Bad])
    by_id = {}
    for issue in issues:
        by_id.setdefault(issue.id, []).append(issue.msg)
    assert len(by_id[validation.E004]) == 2  # the index and the short table
    assert any("'shortidx' is its own IBM i system name" in m for m in by_id[validation.E003])
    assert any("'1BAD'" in m for m in by_id[validation.E003])
