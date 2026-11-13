"""A table in another library than NAME: db_table = 'LIB"."TABLE' or Meta.db_library (#124).

Every constraint and index name on such a table is qualified with its library, also
inside CREATE TABLE; the new name of RENAME INDEX / RENAME TABLE stays unqualified
(probes lib_other_library, qtemp_qualified_names). Introspection looks in the library.
"""

import pytest
from django.db import NotSupportedError, connection, models
from django.db.migrations.state import ModelState
from django.test.utils import isolate_apps

from django_db2_for_i import introspection, validation
from django_db2_for_i.schema import split_table
from tests.offline.test_introspection import CatalogCursor

pytestmark = pytest.mark.offline


def _sql(action) -> list[str]:
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        action(editor)
    return [str(sql).removesuffix(";") for sql in editor.collected_sql]


@pytest.mark.parametrize(
    ("db_table", "expected"),
    [
        ('sales"."orders', ("sales", "orders")),
        ('"SALES"."ORDERS"', ("SALES", "ORDERS")),
        ("orders", ("", "orders")),
    ],
)
def test_split_table(db_table, expected) -> None:
    assert split_table(db_table) == expected


def test_quote_name_qualifies_the_table() -> None:
    assert connection.ops.quote_name('sales"."orders') == '"SALES"."ORDERS"'
    assert connection.ops.quote_name('"SALES"."ORDERS"') == '"SALES"."ORDERS"'
    assert connection.ops.quote_name("orders") == '"ORDERS"'


@isolate_apps("tests.testapp")
def test_create_table_qualifies_every_name() -> None:
    class Parent(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = 'sales"."parent'

    class Order(models.Model):
        parent = models.ForeignKey(Parent, models.CASCADE)
        number = models.IntegerField()
        code = models.CharField(max_length=10)

        class Meta:
            app_label = "testapp"
            db_table = 'sales"."orders'
            constraints = (
                models.UniqueConstraint(fields=["number"], name="order_number_uniq"),
                models.CheckConstraint(
                    condition=models.Q(number__gt=0), name="order_number_positive"
                ),
                models.UniqueConstraint(
                    fields=["code"], condition=models.Q(number__gt=10), name="order_code_uniq"
                ),
            )
            indexes = (models.Index(fields=["code"], name="order_code_idx"),)

    create, *rest = _sql(lambda editor: editor.create_model(Order))
    assert create.startswith('CREATE TABLE "SALES"."ORDERS" (')
    assert 'CONSTRAINT "SALES"."ORDER_NUMBER_UNIQ" UNIQUE ("NUMBER")' in create
    assert 'CONSTRAINT "SALES"."ORDER_NUMBER_POSITIVE" CHECK' in create
    deferred = "\n".join(rest)
    assert 'CREATE INDEX "SALES"."ORDER_CODE_IDX" ON "SALES"."ORDERS"' in deferred
    assert 'INDEX "SALES"."ORDER_CODE_UNIQ" ON "SALES"."ORDERS"' in deferred
    assert 'ALTER TABLE "SALES"."ORDERS" ADD CONSTRAINT "SALES"."' in deferred
    assert 'REFERENCES "SALES"."PARENT" ("ID")' in deferred
    # The foreign key's index too.
    assert deferred.count('INDEX "SALES".') == 3


@isolate_apps("tests.testapp")
def test_constraints_and_indexes_added_and_removed() -> None:
    class Order(models.Model):
        number = models.IntegerField()

        class Meta:
            app_label = "testapp"
            db_table = 'sales"."orders'

    unique = models.UniqueConstraint(fields=["number"], name="order_number_uniq")
    check = models.CheckConstraint(condition=models.Q(number__gt=0), name="order_positive")
    index = models.Index(fields=["number"], name="order_number_idx")
    sql = _sql(
        lambda editor: (
            editor.add_constraint(Order, unique),
            editor.add_constraint(Order, check),
            editor.add_index(Order, index),
            editor.remove_constraint(Order, unique),
            editor.remove_constraint(Order, check),
            editor.remove_index(Order, index),
        )
    )
    assert sql == [
        'ALTER TABLE "SALES"."ORDERS" ADD CONSTRAINT "SALES"."ORDER_NUMBER_UNIQ" UNIQUE ("NUMBER")',
        'ALTER TABLE "SALES"."ORDERS" ADD CONSTRAINT "SALES"."ORDER_POSITIVE" CHECK ("NUMBER" > 0)',
        'CREATE INDEX "SALES"."ORDER_NUMBER_IDX" ON "SALES"."ORDERS" ("NUMBER")',
        'ALTER TABLE "SALES"."ORDERS" DROP CONSTRAINT "SALES"."ORDER_NUMBER_UNIQ"',
        'ALTER TABLE "SALES"."ORDERS" DROP CONSTRAINT "SALES"."ORDER_POSITIVE"',
        'DROP INDEX "SALES"."ORDER_NUMBER_IDX"',
    ]


@isolate_apps("tests.testapp")
def test_renames_keep_the_new_name_unqualified() -> None:
    class Order(models.Model):
        number = models.IntegerField()

        class Meta:
            app_label = "testapp"
            db_table = 'sales"."orders'

    old = models.Index(fields=["number"], name="order_old_idx")
    new = models.Index(fields=["number"], name="order_new_idx")
    sql = _sql(
        lambda editor: (
            editor.rename_index(Order, old, new),
            editor.alter_db_table(Order, 'sales"."orders', 'sales"."orders_2026'),
        )
    )
    assert sql == [
        'RENAME INDEX "SALES"."ORDER_OLD_IDX" TO "ORDER_NEW_IDX"',
        'RENAME TABLE "SALES"."ORDERS" TO "ORDERS_2026"',
    ]


@isolate_apps("tests.testapp")
def test_a_table_cannot_move_to_another_library() -> None:
    class Order(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = 'sales"."orders'

    for old, new in (('sales"."orders', 'archive"."orders'), ('sales"."orders', "orders")):
        with pytest.raises(NotSupportedError, match="keeps a table in its library"):
            _sql(lambda editor, old=old, new=new: editor.alter_db_table(Order, old, new))


@isolate_apps("tests.testapp")
def test_a_table_in_name_is_unchanged() -> None:
    class Order(models.Model):
        number = models.IntegerField(unique=True)

        class Meta:
            app_label = "testapp"
            db_table = "orders"
            indexes = (models.Index(fields=["number"], name="order_number_idx"),)

    create, index = _sql(lambda editor: editor.create_model(Order))
    assert create.startswith('CREATE TABLE "ORDERS" (')
    assert index == 'CREATE INDEX "ORDER_NUMBER_IDX" ON "ORDERS" ("NUMBER")'
    renamed = _sql(lambda editor: editor.alter_db_table(Order, "orders", "orders_2026"))
    assert renamed == ['RENAME TABLE "ORDERS" TO "ORDERS_2026"']


# --- Meta.db_library (apps.py) -----------------------------------------------------


def test_meta_db_library_is_an_accepted_option() -> None:
    from django.db.migrations import state
    from django.db.models import options

    assert "db_library" in options.DEFAULT_NAMES
    assert "db_library" in state.DEFAULT_NAMES


@isolate_apps("tests.testapp")
def test_db_library_qualifies_db_table() -> None:
    class Invoice(models.Model):
        class Meta:
            app_label = "testapp"
            db_library = "sales"

    class Payment(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "payments"
            db_library = "SALES"

    assert Invoice._meta.db_table == 'SALES"."testapp_invoice'
    assert Payment._meta.db_table == 'SALES"."payments'
    assert validation.check_db_library(Invoice) == []
    (create,) = _sql(lambda editor: editor.create_model(Payment))
    assert create.startswith('CREATE TABLE "SALES"."PAYMENTS" (')


@isolate_apps("tests.testapp")
def test_migrations_keep_db_library() -> None:
    class Invoice(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = "invoices"
            db_library = "SALES"

    model_state = ModelState.from_model(Invoice)
    assert model_state.options["db_library"] == "SALES"
    assert model_state.options["db_table"] == "invoices"
    rendered = model_state.render(Invoice._meta.apps.__class__())
    assert rendered._meta.db_table == 'SALES"."invoices'


@isolate_apps("tests.testapp")
def test_e005() -> None:
    class Twice(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = 'archive"."twice'
            db_library = "SALES"

    class Invalid(models.Model):
        class Meta:
            app_label = "testapp"
            db_library = "1SALES"

    class Same(models.Model):
        class Meta:
            app_label = "testapp"
            db_table = 'sales"."same'
            db_library = "SALES"

    (twice,) = validation.check_db_library(Twice)
    assert twice.id == validation.E005
    assert "two libraries" in twice.msg
    (invalid,) = validation.check_db_library(Invalid)
    assert invalid.id == validation.E005
    assert "not a valid IBM i library name" in invalid.msg
    assert validation.check_db_library(Same) == []


@isolate_apps("tests.testapp")
def test_system_names_of_tables_in_two_libraries_do_not_clash() -> None:
    def model(name, db_table):
        meta = type(
            "Meta",
            (),
            {"app_label": "testapp", "db_table": db_table, "db_system_name": "ORDLIN"},
        )
        return type(name, (models.Model,), {"__module__": __name__, "Meta": meta})

    first = model("First", 'sales"."order_lines')
    second = model("Second", 'archive"."order_lines')
    third = model("Third", 'sales"."order_rows_2026')
    assert validation.check_object_system_names([first, second]) == []
    (clash,) = validation.check_object_system_names([first, third])
    assert clash.id == validation.E004


# --- Introspection -----------------------------------------------------------------


def test_introspection_reads_the_library() -> None:
    cursor = CatalogCursor({})
    intro = connection.introspection
    intro.get_constraints(cursor, 'sales"."orders')
    intro.get_relations(cursor, 'sales"."orders')
    intro.get_sequences(cursor, 'sales"."orders')
    for sql, params in cursor.executed:
        assert "CURRENT SCHEMA" not in sql
        assert sql.count("TABLE_SCHEMA = %s AND") == sql.count("TABLE_NAME = %s")
        assert params == ["SALES", "ORDERS"] * sql.count("TABLE_NAME = %s")
    constraints_sql, _params = cursor.executed[0]
    assert constraints_sql == introspection.CONSTRAINTS_SQL.replace(
        "TABLE_SCHEMA = CURRENT SCHEMA", "TABLE_SCHEMA = %s"
    )


def test_introspection_of_a_plain_name_is_unchanged() -> None:
    cursor = CatalogCursor({})
    connection.introspection.get_relations(cursor, "orders")
    assert cursor.executed == [(introspection.RELATIONS_SQL, ["ORDERS"])]
