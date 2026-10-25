"""Foreign key violations against the IBM i: SQL0530 / SQL0531 / SQL0532 raise
IntegrityError (writes).

The tests.testapp tables are created for this module with their foreign key
constraints (``testapp_tables`` in conftest.py enables foreign keys while it
creates them) and dropped again. Db2 for i reports these violations with
SQLSTATE HY000; the driver layer classifies them by SQLCODE.

The facts a-d further down (docs/IBMI_NOTES.md, "Foreign keys through the
schema editor") use a parent and a child model of their own.

Link.code is a ForeignKey to Code, whose primary key is a CharField (no
identity column), so its parent key can be updated. The violations are
written with QuerySet.update() and a plain DELETE: Model.delete() would run
Django's on_delete=CASCADE first and never reach the constraint.
"""

import pytest
from django.db import IntegrityError

from tests.testapp.models import Code, Link

pytestmark = pytest.mark.usefixtures("testapp_tables")


def sqlcode(excinfo) -> int | None:
    return getattr(excinfo.value.__cause__, "sqlcode", None)


def test_insert_child_without_parent(live, empty) -> None:
    """SQL0530: INSERT of a child row whose key has no parent row."""
    with pytest.raises(IntegrityError, match="SQL0530") as excinfo:
        Link.objects.create(code_id="MISSING")
    assert sqlcode(excinfo) == -530
    assert not Link.objects.exists()


def test_update_child_to_missing_parent(live, empty) -> None:
    """SQL0530: UPDATE of a child row to a key without a parent row."""
    Code.objects.create(code="C-1")
    link = Link.objects.create(code_id="C-1")
    with pytest.raises(IntegrityError, match="SQL0530") as excinfo:
        Link.objects.filter(pk=link.pk).update(code_id="MISSING")
    assert sqlcode(excinfo) == -530
    assert Link.objects.get(pk=link.pk).code_id == "C-1"


def test_update_referenced_parent_key(live, empty) -> None:
    """SQL0531: UPDATE of a parent key that a child row refers to."""
    Code.objects.create(code="C-1")
    Link.objects.create(code_id="C-1")
    with pytest.raises(IntegrityError, match="SQL0531") as excinfo:
        Code.objects.filter(pk="C-1").update(code="C-2")
    assert sqlcode(excinfo) == -531
    assert list(Code.objects.values_list("code", flat=True)) == ["C-1"]


def test_delete_referenced_parent(live, empty) -> None:
    """SQL0532: DELETE of a parent row that a child row refers to."""
    Code.objects.create(code="C-1")
    Link.objects.create(code_id="C-1")
    table = live.ops.quote_name(Code._meta.db_table)
    column = live.ops.quote_name(Code._meta.pk.column)
    with pytest.raises(IntegrityError, match="SQL0532") as excinfo, live.cursor() as cursor:
        cursor.execute(f"DELETE FROM {table} WHERE {column} = %s", ["C-1"])
    assert sqlcode(excinfo) == -532
    assert Code.objects.filter(pk="C-1").exists()


# --- Foreign keys through the schema editor (facts for supports_foreign_keys) ----------
#
# A parent and a child model of their own, created with foreign keys enabled
# (supports_foreign_keys is still off), as a migration with the flag on would
# create them. Every result is also printed (run with -s) for docs/IBMI_NOTES.md.

FK_TABLES = ("TESTAPP_FKCHILD", "TESTAPP_FKPARENT", "TESTAPP_FKCHILD2", "TESTAPP_FKPARENT2")


def _existing(live, *names: str) -> set[str]:
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = CURRENT SCHEMA "
            f"AND TABLE_NAME IN ({', '.join(['%s'] * len(names))})",
            list(names),
        )
        return {row[0] for row in cursor.fetchall()}


def _column_type(live, table: str, column: str) -> str | None:
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT DATA_TYPE FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = CURRENT SCHEMA "
            "AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            [table.upper(), column.upper()],
        )
        row = cursor.fetchone()
    return row[0].strip() if row else None


def _foreign_keys(live, table: str) -> dict[str, tuple]:
    with live.cursor() as cursor:
        constraints = live.introspection.get_constraints(cursor, table)
    return {
        name: (tuple(info["columns"]), info["foreign_key"])
        for name, info in constraints.items()
        if info["foreign_key"]
    }


@pytest.fixture
def fk_models(live, monkeypatch):
    """FkParent (AutoField pk) and FkChild (ForeignKey to it), created with
    their foreign key; dropped after the test (whichever names exist)."""
    from django.apps import apps
    from django.db import models

    from tests.pub400.connection_guard import replace_if_unusable

    monkeypatch.setattr(live.features, "supports_foreign_keys", True)

    class FkParent(models.Model):
        name = models.CharField(max_length=20)

        class Meta:
            app_label = "testapp"

    class FkChild(models.Model):
        parent = models.ForeignKey(FkParent, models.PROTECT)
        note = models.CharField(max_length=20, default="")

        class Meta:
            app_label = "testapp"

    try:
        with live.schema_editor() as editor:
            editor.create_model(FkParent)
            editor.create_model(FkChild)
        yield FkParent, FkChild
    finally:
        replace_if_unusable(live)
        for table in FK_TABLES:  # children first: no foreign key blocks a DROP
            if _existing(live, table):
                with live.cursor() as cursor:
                    cursor.execute(f'DROP TABLE "{table}"')
        for name in ("fkparent", "fkchild"):
            apps.all_models["testapp"].pop(name, None)
        apps.clear_cache()


def _rebuilt(model, name, cls, **changes):
    old = model._meta.get_field(name)
    _name, _path, args, kwargs = old.deconstruct()
    field = cls(*args, **{**kwargs, **changes})
    field.set_attributes_from_name(name)
    field.model = model
    return field


@pytest.fixture
def fk_cleanup(live, monkeypatch):
    """Foreign keys enabled; the fk tables dropped after the test."""
    from tests.pub400.connection_guard import replace_if_unusable

    monkeypatch.setattr(live.features, "supports_foreign_keys", True)
    yield
    replace_if_unusable(live)
    for table in FK_TABLES:
        if _existing(live, table):
            with live.cursor() as cursor:
                cursor.execute(f'DROP TABLE "{table}"')


def test_fact_a_primary_key_type_change_with_an_incoming_foreign_key(live, fk_cleanup) -> None:
    """AutoField -> BigAutoField on a parent that a child refers to, as a
    migration (MigrationExecutor, the models rebuilt from the migration
    state): Django drops the incoming foreign key, changes the parent key and
    the child's column, and adds the foreign key again."""
    from django.db import migrations, models
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.state import ProjectState

    create = migrations.Migration("0001_create", "testapp")
    create.operations = [
        migrations.CreateModel("FkParent", [("id", models.AutoField(primary_key=True))]),
        migrations.CreateModel(
            "FkChild",
            [
                ("id", models.AutoField(primary_key=True)),
                ("parent", models.ForeignKey("testapp.FkParent", models.PROTECT)),
            ],
        ),
    ]
    alter = migrations.Migration("0002_bigger", "testapp")
    alter.operations = [
        migrations.AlterField("fkparent", "id", models.BigAutoField(primary_key=True)),
    ]
    executor = MigrationExecutor(live)
    state = executor.apply_migration(ProjectState(), create)
    with live.cursor() as cursor:
        cursor.execute('INSERT INTO "TESTAPP_FKPARENT" ("ID") VALUES (DEFAULT)')
        cursor.execute('SELECT "ID" FROM "TESTAPP_FKPARENT"')
        (parent_id,) = cursor.fetchone()
        cursor.execute('INSERT INTO "TESTAPP_FKCHILD" ("PARENT_ID") VALUES (%s)', [parent_id])
    executor.apply_migration(state, alter)
    types = (
        _column_type(live, "TESTAPP_FKPARENT", "ID"),
        _column_type(live, "TESTAPP_FKCHILD", "PARENT_ID"),
    )
    fks = _foreign_keys(live, "testapp_fkchild")
    print(f"\nFACT a: parent ID {types[0]}, child PARENT_ID {types[1]}, foreign keys {fks}")
    assert types == ("BIGINT", "BIGINT")
    assert list(fks.values()) == [(("parent_id",), ("testapp_fkparent", "id"))]
    with pytest.raises(IntegrityError, match="SQL0530"), live.cursor() as cursor:
        cursor.execute('INSERT INTO "TESTAPP_FKCHILD" ("PARENT_ID") VALUES (%s)', [999])


def _orphan_insert(live) -> str:
    from django.db import DatabaseError

    try:
        with live.cursor() as cursor:
            cursor.execute(
                'INSERT INTO "TESTAPP_FKCHILD" ("PARENT_ID", "NOTE") VALUES (%s, %s)', [999, "x"]
            )
    except DatabaseError as exc:
        return f"refused SQL{abs(getattr(exc.__cause__, 'sqlcode', 0) or 0):04d}"
    return "accepted"


def _catalog_constraints(live, table: str) -> list[tuple]:
    with live.cursor() as cursor:
        cursor.execute(
            "SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE, ENABLED, CHECK_PENDING FROM QSYS2.SYSCST "
            "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME = %s ORDER BY CONSTRAINT_NAME",
            [table],
        )
        return [tuple(v.strip() if isinstance(v, str) else v for v in row) for row in cursor]


@pytest.mark.parametrize(
    ("label", "sql"),
    [
        (
            "child column",
            'ALTER TABLE "TESTAPP_FKCHILD" ALTER COLUMN "PARENT_ID" SET DATA TYPE BIGINT',
        ),
        ("parent key", 'ALTER TABLE "TESTAPP_FKPARENT" ALTER COLUMN "ID" SET DATA TYPE BIGINT'),
    ],
)
def test_fact_b_type_change_of_a_column_in_a_foreign_key(live, fk_models, label, sql) -> None:
    """SET DATA TYPE on a column that is part of a foreign key, while the
    foreign key exists, is accepted, but Db2 for i silently stops enforcing
    the foreign key: it stays in SYSCST with ENABLED and CHECK_PENDING empty
    (before: YES / NO), and a row without a parent is accepted. Introspection
    reads that state and no longer lists it as a foreign key. Django drops
    the foreign key before a type change and adds it again (fact a); the
    backend must never change such a column without that."""
    fk = ("FOREIGN KEY", "YES", "NO")
    assert [c[1:] for c in _catalog_constraints(live, "TESTAPP_FKCHILD")][1:] == [fk]
    assert _orphan_insert(live) == "refused SQL0530"
    with live.cursor() as cursor:
        cursor.execute(sql)
    print(f"\nFACT b ({label}): SYSCST {_catalog_constraints(live, 'TESTAPP_FKCHILD')}")
    assert [c[1:] for c in _catalog_constraints(live, "TESTAPP_FKCHILD")][1:] == [
        ("FOREIGN KEY", None, None)
    ]
    assert _foreign_keys(live, "testapp_fkchild") == {}
    assert _orphan_insert(live) == "accepted"


def test_fact_c_rename_tables_with_foreign_keys(live, fk_models) -> None:
    """RENAME TABLE of the parent and of the child keeps the foreign key: it
    then refers to the new parent name, and a violation is still refused."""
    parent, child = fk_models
    try:
        with live.schema_editor() as editor:
            editor.alter_db_table(parent, "testapp_fkparent", "testapp_fkparent2")
            editor.alter_db_table(child, "testapp_fkchild", "testapp_fkchild2")
        fks = _foreign_keys(live, "testapp_fkchild2")
        print(f"\nFACT c: foreign keys after both renames {fks}")
        assert list(fks.values()) == [(("parent_id",), ("testapp_fkparent2", "id"))]
        with pytest.raises(IntegrityError, match="SQL0530"), live.cursor() as cursor:
            cursor.execute(
                'INSERT INTO "TESTAPP_FKCHILD2" ("PARENT_ID", "NOTE") VALUES (%s, %s)', [999, "x"]
            )
    finally:
        with live.schema_editor() as editor:
            if _existing(live, "TESTAPP_FKCHILD2"):
                editor.alter_db_table(child, "testapp_fkchild2", "testapp_fkchild")
            if _existing(live, "TESTAPP_FKPARENT2"):
                editor.alter_db_table(parent, "testapp_fkparent2", "testapp_fkparent")


def test_fact_d_foreign_key_to_plain_field(live, fk_models) -> None:
    """AlterField ForeignKey -> IntegerField: Django finds the foreign key by
    introspection and drops it; the values stay."""
    from django.db import models

    parent, child = fk_models
    p = parent.objects.create(name="p")
    child.objects.create(parent=p)
    old = child._meta.get_field("parent")
    new = models.IntegerField()
    new.set_attributes_from_name("parent_id")
    new.column = "parent_id"
    new.model = child
    with live.schema_editor() as editor:
        editor.alter_field(child, old, new, strict=True)
    fks = _foreign_keys(live, "testapp_fkchild")
    print(f"\nFACT d: foreign keys after AlterField {fks}")
    assert fks == {}
    with live.cursor() as cursor:
        cursor.execute('SELECT "PARENT_ID" FROM "TESTAPP_FKCHILD"')
        assert cursor.fetchall() == [(p.pk,)]
        # No constraint any more: a value without a parent is accepted.
        cursor.execute(
            'INSERT INTO "TESTAPP_FKCHILD" ("PARENT_ID", "NOTE") VALUES (%s, %s)', [999, "x"]
        )


# --- Foreign keys stay enforced after every type-change path (supports_foreign_keys) ---
#
# Fact b: SET DATA TYPE on a column of a foreign key silently stops enforcing
# it. Django drops a foreign key around a type change and adds it again; these
# migrations check, for each path, that every foreign key is enforced
# afterwards (SYSCST ENABLED = YES and a row without a parent refused), not
# only visible in introspection.

PATH_TABLES = ("TESTAPP_FKGRAND", "TESTAPP_FKCHILD", "TESTAPP_FKOTHER", "TESTAPP_FKPARENT")


@pytest.fixture
def path_cleanup(live):
    from tests.pub400.connection_guard import replace_if_unusable

    yield MigrationRunner(live)
    replace_if_unusable(live)
    for table in PATH_TABLES:  # children first
        if _existing(live, table):
            with live.cursor() as cursor:
                cursor.execute(f'DROP TABLE "{table}"')


class MigrationRunner:
    """Applies migrations of the app "testapp" in order, as migrate does."""

    def __init__(self, live):
        from django.db.migrations.executor import MigrationExecutor
        from django.db.migrations.state import ProjectState

        self.executor = MigrationExecutor(live)
        self.state = ProjectState()
        self.count = 0

    def apply(self, *operations):
        from django.db import migrations

        self.count += 1
        migration = migrations.Migration(f"{self.count:04d}_step", "testapp")
        migration.operations = list(operations)
        self.state = self.executor.apply_migration(self.state, migration)


def _assert_enforced(live, child_table: str, column: str, value) -> None:
    """The child's foreign keys are enabled in SYSCST and refuse a value
    without a parent."""
    states = [c[1:3] for c in _catalog_constraints(live, child_table) if c[1] == "FOREIGN KEY"]
    assert states and all(state == ("FOREIGN KEY", "YES") for state in states), states
    with pytest.raises(IntegrityError, match="SQL0530"), live.cursor() as cursor:
        cursor.execute(f'INSERT INTO "{child_table}" ("{column}") VALUES (%s)', [value])


def test_enforced_after_primary_key_type_change(live, path_cleanup) -> None:
    from django.db import migrations, models

    runner = path_cleanup
    runner.apply(
        migrations.CreateModel("FkParent", [("id", models.AutoField(primary_key=True))]),
        migrations.CreateModel(
            "FkChild",
            [
                ("id", models.AutoField(primary_key=True)),
                ("parent", models.ForeignKey("testapp.FkParent", models.PROTECT)),
            ],
        ),
    )
    runner.apply(migrations.AlterField("fkparent", "id", models.BigAutoField(primary_key=True)))
    assert _column_type(live, "TESTAPP_FKCHILD", "PARENT_ID") == "BIGINT"
    _assert_enforced(live, "TESTAPP_FKCHILD", "PARENT_ID", 999)


def test_enforced_after_a_transitive_primary_key_type_change(live, path_cleanup) -> None:
    """The child's primary key is a OneToOneField to the parent (like Profile
    to Author), and a grandchild refers to the child (like Link to Profile):
    the parent's key change also changes the child's key, which the
    grandchild's foreign key refers to."""
    from django.db import migrations, models

    runner = path_cleanup
    runner.apply(
        migrations.CreateModel("FkParent", [("id", models.AutoField(primary_key=True))]),
        migrations.CreateModel(
            "FkChild",
            [
                (
                    "parent",
                    models.OneToOneField(
                        "testapp.FkParent", models.CASCADE, primary_key=True, serialize=False
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            "FkGrand",
            [
                ("id", models.AutoField(primary_key=True)),
                ("child", models.ForeignKey("testapp.FkChild", models.PROTECT)),
            ],
        ),
    )
    runner.apply(migrations.AlterField("fkparent", "id", models.BigAutoField(primary_key=True)))
    types = [
        _column_type(live, "TESTAPP_FKCHILD", "PARENT_ID"),
        _column_type(live, "TESTAPP_FKGRAND", "CHILD_ID"),
    ]
    print(
        f"\nTRANSITIVE: child PARENT_ID {types[0]}, grandchild CHILD_ID {types[1]}; "
        f"grandchild SYSCST {_catalog_constraints(live, 'TESTAPP_FKGRAND')}"
    )
    _assert_enforced(live, "TESTAPP_FKCHILD", "PARENT_ID", 999)
    _assert_enforced(live, "TESTAPP_FKGRAND", "CHILD_ID", 999)


def test_enforced_after_a_to_field_target_widens(live, path_cleanup) -> None:
    from django.db import migrations, models

    runner = path_cleanup
    runner.apply(
        migrations.CreateModel(
            "FkParent",
            [
                ("id", models.AutoField(primary_key=True)),
                ("code", models.CharField(max_length=10, unique=True)),
            ],
        ),
        migrations.CreateModel(
            "FkChild",
            [
                ("id", models.AutoField(primary_key=True)),
                (
                    "parent",
                    models.ForeignKey("testapp.FkParent", models.PROTECT, to_field="code"),
                ),
            ],
        ),
    )
    runner.apply(
        migrations.AlterField("fkparent", "code", models.CharField(max_length=20, unique=True))
    )
    assert _column_type(live, "TESTAPP_FKCHILD", "PARENT_ID") == "VARG"
    _assert_enforced(live, "TESTAPP_FKCHILD", "PARENT_ID", "MISSING")


def test_enforced_after_a_foreign_key_moves_to_another_parent_type(live, path_cleanup) -> None:
    from django.db import migrations, models

    runner = path_cleanup
    runner.apply(
        migrations.CreateModel("FkParent", [("id", models.AutoField(primary_key=True))]),
        migrations.CreateModel("FkOther", [("id", models.BigAutoField(primary_key=True))]),
        migrations.CreateModel(
            "FkChild",
            [
                ("id", models.AutoField(primary_key=True)),
                ("parent", models.ForeignKey("testapp.FkParent", models.PROTECT)),
            ],
        ),
    )
    runner.apply(
        migrations.AlterField(
            "fkchild", "parent", models.ForeignKey("testapp.FkOther", models.PROTECT)
        )
    )
    assert _column_type(live, "TESTAPP_FKCHILD", "PARENT_ID") == "BIGINT"
    _assert_enforced(live, "TESTAPP_FKCHILD", "PARENT_ID", 999)
