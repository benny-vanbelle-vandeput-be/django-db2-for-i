"""DDL goldens: CREATE TABLE per type rule, ALTER TABLE, DROP TABLE.

The schema editors only collect SQL, with atomic=False: with can_rollback_ddl
an atomic one enters transaction.atomic(), which opens a connection.
"""

from __future__ import annotations

from django.db.models import (
    NOT_PROVIDED,
    PROTECT,
    SET_NULL,
    BigAutoField,
    BigIntegerField,
    CharField,
    CheckConstraint,
    ForeignKey,
    Index,
    IntegerField,
    OneToOneField,
    Q,
)

from tests.golden_cases.base import (
    ACCOUNT,
    AUTHOR,
    BOOK,
    CODE,
    CONTACT,
    DEFAULTS,
    LINK,
    MEASURE,
    NODE,
    PROFILE,
    RATING,
    SCHEDULE,
    SWITCH,
    TAG,
    Case,
)
from tests.testapp.models import (
    Account,
    Article,
    Author,
    Book,
    Code,
    Contact,
    Defaults,
    Document,
    Link,
    Measure,
    Node,
    Profile,
    Rating,
    Schedule,
    Switch,
    Tag,
)


def _ddl(*models):
    """CREATE TABLE as create_model() writes it, with the deferred foreign
    keys (ALTER TABLE ... ADD CONSTRAINT) and indexes."""

    def build(connection):
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            for model in models:
                editor.create_model(model)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _add_not_null_with_python_default(connection):
    """AddField of a NOT NULL column with a Python default (literal, then dropped)."""
    field = CharField(max_length=20, default="O'Brien")
    field.set_attributes_from_name("nickname")
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.add_field(Defaults, field)
    return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]


def _remove_field(model, name):
    """RemoveField: ALTER TABLE ... DROP COLUMN, the same on every Django version."""

    def build(connection):
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.remove_field(model, model._meta.get_field(name))
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _field(model, name, cls=None, **changes):
    """``model``'s field ``name``, rebuilt with ``changes`` (NOT_PROVIDED removes one)."""
    old = model._meta.get_field(name)
    _name, _path, args, kwargs = old.deconstruct()
    kwargs.update(changes)
    kwargs = {key: value for key, value in kwargs.items() if value is not NOT_PROVIDED}
    field = (cls or type(old))(*args, **kwargs)
    field.set_attributes_from_name(name)
    field.model = model
    return field


def _alter(model, *changes):
    """AlterField, one ``(old, new)`` pair of fields per change (built by _field)."""

    def build(connection):
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            for old, new in changes:
                editor.alter_field(model, old(), new(), strict=True)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _rename_table_and_back(model, new_name):
    """RenameModel: RENAME TABLE, and back, so the later goldens find the table."""

    def build(connection):
        old_name = model._meta.db_table
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.alter_db_table(model, old_name, new_name)
            editor.alter_db_table(model, new_name, old_name)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _rename_index_and_back(model, fields, old_name, new_name):
    """RenameIndex: RENAME INDEX (can_rename_index), and back."""

    def build(connection):
        old, new = Index(fields=fields, name=old_name), Index(fields=fields, name=new_name)
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.rename_index(model, old, new)
            editor.rename_index(model, new, old)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _add_and_remove_index(model, index):
    """AddIndex and RemoveIndex: CREATE INDEX (with DESC columns,
    supports_index_column_ordering) and DROP INDEX."""

    def build(connection):
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.add_index(model, index)
            editor.remove_index(model, index)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _add_and_remove_constraint(model, constraint):
    """AddConstraint and RemoveConstraint: ALTER TABLE ... ADD / DROP CONSTRAINT."""

    def build(connection):
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.add_constraint(model, constraint)
            editor.remove_constraint(model, constraint)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _drop_and_add_foreign_keys(model):
    """DROP CONSTRAINT of each of ``model``'s foreign keys (create_model() added
    them), then ADD CONSTRAINT ... FOREIGN KEY again by the same name. (Dropping
    one in RemoveField / AlterField finds the name by introspection, which needs
    a connection; the IBM i tests cover that part.)"""

    def build(connection):
        suffix = "_fk_%(to_table)s_%(to_column)s"
        fields = [field for field in model._meta.local_fields if field.remote_field]
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            for field in fields:
                name = editor._fk_constraint_name(model, field, suffix)
                editor.execute(editor._delete_fk_sql(model, str(name)))
            for field in fields:
                editor.execute(editor._create_fk_sql(model, field, suffix))
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _add_relation(model, name, make_field):
    """AddField of a relation: ADD COLUMN, ADD CONSTRAINT and (except for a
    OneToOneField) Django's index, then DROP CONSTRAINT of the foreign key
    again, so no constraint is left that refers to the parent table. The
    column stays: DROP COLUMN is cancelled by CPA32B2 on PUB400."""

    def build(connection):
        field = make_field()
        field.set_attributes_from_name(name)
        field.model = model
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.add_field(model, field)
            fk_name = editor._fk_constraint_name(model, field, "_fk_%(to_table)s_%(to_column)s")
            # The foreign key is deferred SQL: drop it after it.
            editor.deferred_sql.append(editor._delete_fk_sql(model, str(fk_name)))
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _add_column(model, name, make_field):
    """AddField without foreign keys (as a migration's AddField has it)."""

    def build(connection):
        field = make_field()
        field.set_attributes_from_name(name)
        field.model = model
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.add_field(model, field)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _drop(model):
    def build(connection):
        with connection.schema_editor(collect_sql=True, atomic=False) as editor:
            editor.delete_model(model)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


CASES: tuple[Case, ...] = (
    # DDL types: identity columns, NVARCHAR, TIMESTAMP(6), TIME, BOOLEAN,
    # CHECK, UUID as CHAR(32), UNIQUE, indexes, NO ACTION foreign key.
    Case(AUTHOR, "create", _ddl(Author)),
    Case(BOOK, "create", _ddl(Book), (AUTHOR,)),
    Case(NODE, "create", _ddl(Node)),
    Case(TAG, "create", _ddl(Tag)),
    # Column DEFAULT literals, one per prepare_default() rule (no CAST).
    Case(DEFAULTS, "create", _ddl(Defaults)),
    # TextField and BinaryField: NCLOB and BLOB (1M, the default length).
    Case("ddl/create_document", "create", _ddl(Document)),
    # DurationField: BIGINT microseconds.
    Case(SCHEDULE, "create", _ddl(Schedule)),
    # Foreign keys to integer, CharField, UUID and key primary keys; an IP.
    Case(CODE, "create", _ddl(Code)),
    Case(PROFILE, "create", _ddl(Profile), (AUTHOR,)),
    Case(LINK, "create", _ddl(Link), (AUTHOR, CODE, TAG, PROFILE)),
    # A composite UNIQUE key, the target of a two-column ForeignObject.
    Case(ACCOUNT, "create", _ddl(Account)),
    Case(CONTACT, "create", _ddl(Contact)),
    # A nullable BOOLEAN column.
    Case(SWITCH, "create", _ddl(Switch)),
    # SMALLINT, DECIMAL(5, 2) and BIGINT columns (issue #69).
    Case(MEASURE, "create", _ddl(Measure)),
    # CHECK constraints: a column check and two model CheckConstraints (a
    # column against a column, string literals with a quote).
    Case(RATING, "create", _ddl(Rating)),
    # Fields from an abstract mixin and an abstract base: column order (#23).
    Case("ddl/create_article", "create", _ddl(Article)),
    # Foreign keys: each foreign key of Link (create_link added them), to an
    # INTEGER, NVARCHAR, CHAR(32) (UUID) and key-to-a-key primary key, dropped
    # and added again; AddField of a nullable ForeignKey, of one to a
    # non-primary-key UNIQUE column (to_field), and of a OneToOneField (UNIQUE,
    # no extra index), each foreign key dropped again, so no later golden
    # changes a table a foreign key refers to (Db2 for i rejects a foreign key
    # whose column type differs from the parent key's, SQL0538, and silently
    # stops enforcing one whose column changes type: IBMI_NOTES).
    Case(
        "ddl/add_foreign_keys",
        "alter",
        _drop_and_add_foreign_keys(Link),
        (LINK, AUTHOR, CODE, TAG, PROFILE),
    ),
    Case(
        "ddl/add_field_foreign_key",
        "alter",
        _add_relation(Schedule, "author", lambda: ForeignKey(Author, PROTECT, null=True)),
        (SCHEDULE, AUTHOR),
    ),
    Case(
        "ddl/add_field_foreign_key_to_field",
        "alter",
        _add_relation(
            Schedule, "tag", lambda: ForeignKey(Tag, SET_NULL, null=True, to_field="label")
        ),
        (SCHEDULE, TAG),
    ),
    Case(
        "ddl/add_field_one_to_one",
        "alter",
        _add_relation(Switch, "author", lambda: OneToOneField(Author, PROTECT, null=True)),
        (SWITCH, AUTHOR),
    ),
    # AddField of a NOT NULL column without any default: Db2 for i needs a
    # DEFAULT with NOT NULL (SQL0109), so a bare DEFAULT (the system default),
    # dropped right after; at migrate time a table with rows is refused first
    # (schema.py add_field(); sqlmigrate shows this form). Also UNIQUE, and a
    # NOT NULL foreign key (dropped again, like the foreign key goldens above).
    Case(
        "ddl/add_field_not_null_no_default",
        "alter",
        _add_column(Schedule, "position", lambda: BigIntegerField()),
        (SCHEDULE,),
    ),
    Case(
        "ddl/add_field_not_null_unique",
        "alter",
        _add_column(Schedule, "slug", lambda: CharField(max_length=20, unique=True)),
        (SCHEDULE,),
    ),
    Case(
        "ddl/add_field_foreign_key_not_null",
        "alter",
        _add_relation(Schedule, "owner", lambda: ForeignKey(Author, PROTECT)),
        (SCHEDULE, AUTHOR),
    ),
    # "alter", like the other added columns: as a "create" golden its NOT NULL
    # column without a default broke the insert of dml/insert_returning_db_defaults.
    Case(
        "ddl/add_field_not_null_default",
        "alter",
        _add_not_null_with_python_default,
        (DEFAULTS,),
    ),
    # AlterField: ALTER COLUMN ... SET DATA TYPE (Db2 for i has no TYPE form)
    # for widening changes, DROP NOT NULL, SET / DROP DEFAULT; they run after
    # the queries ("alter"), on the emptied table.
    Case(
        "ddl/alter_field_widen",
        "alter",
        _alter(
            Defaults,
            (lambda: _field(Defaults, "text"), lambda: _field(Defaults, "text", max_length=40)),
            (
                lambda: _field(Defaults, "number"),
                lambda: _field(Defaults, "number", BigIntegerField),
            ),
            (
                lambda: _field(Defaults, "amount"),
                lambda: _field(Defaults, "amount", max_digits=7, decimal_places=3),
            ),
        ),
        (DEFAULTS,),
    ),
    Case(
        "ddl/alter_field_null",
        "alter",
        _alter(
            Defaults,
            (lambda: _field(Defaults, "number"), lambda: _field(Defaults, "number", null=True)),
        ),
        (DEFAULTS,),
    ),
    Case(
        "ddl/alter_field_default",
        "alter",
        _alter(
            Defaults,
            (lambda: _field(Defaults, "text"), lambda: _field(Defaults, "text", db_default="Ж €")),
            (
                lambda: _field(Defaults, "flag"),
                lambda: _field(Defaults, "flag", db_default=NOT_PROVIDED),
            ),
        ),
        (DEFAULTS,),
    ),
    # RenameModel and RenameIndex: RENAME TABLE / RENAME INDEX, each and back.
    Case(
        "ddl/rename_table",
        "alter",
        _rename_table_and_back(Switch, "testapp_lightswitch"),
        (SWITCH,),
    ),
    Case(
        "ddl/add_index_descending",
        "alter",
        _add_and_remove_index(
            Book, Index(fields=["-published", "title"], name="testapp_book_pub_desc")
        ),
        (BOOK,),
    ),
    Case(
        "ddl/rename_index",
        "alter",
        _rename_index_and_back(
            Book, ["title"], "testapp_book_title_c797b345", "testapp_book_title_idx"
        ),
        (BOOK,),
    ),
    # Identity changes: AutoField -> IntegerField drops the identity;
    # IntegerField -> AutoField adds it and restarts after MAX(); AutoField ->
    # BigAutoField widens it. On Measure, which no foreign key refers to (a
    # primary key with incoming foreign keys: own IBM i tests, migrations).
    Case(
        "ddl/alter_field_identity",
        "alter",
        _alter(
            Measure,
            (lambda: _field(Measure, "id"), lambda: _field(Measure, "id", IntegerField)),
            (lambda: _field(Measure, "id", IntegerField), lambda: _field(Measure, "id")),
            (lambda: _field(Measure, "id"), lambda: _field(Measure, "id", BigAutoField)),
        ),
        (MEASURE,),
    ),
    # The way back: narrowing and NOT NULL, which send CPA32B2 (suppressed, as in
    # migrations: tests/ibmi/test_goldens.py).
    Case(
        "ddl/alter_field_narrow",
        "alter",
        _alter(
            Defaults,
            (lambda: _field(Defaults, "text", max_length=40), lambda: _field(Defaults, "text")),
        ),
        (DEFAULTS,),
    ),
    Case(
        "ddl/alter_field_not_null",
        "alter",
        _alter(
            Defaults,
            (lambda: _field(Defaults, "number", null=True), lambda: _field(Defaults, "number")),
        ),
        (DEFAULTS,),
    ),
    # AddConstraint / RemoveConstraint of a CheckConstraint. Changing a column
    # check (#151) needs the name Db2 for i gave it, which holds the library
    # name: tests/offline/test_schema.py and the IBM i tests cover it.
    Case(
        "ddl/add_check_constraint",
        "alter",
        _add_and_remove_constraint(
            Rating, CheckConstraint(condition=Q(stars__lte=5), name="testapp_rating_stars_lte_5")
        ),
        (RATING,),
    ),
    # DROP COLUMN without CASCADE / RESTRICT on every Django version (probe 23).
    Case("ddl/remove_field", "drop", _remove_field(Defaults, "ratio"), (DEFAULTS,)),
    # DROP TABLE (cascades on Db2 for i).
    Case("ddl/drop_tag", "drop", _drop(Tag), (TAG,)),
)
