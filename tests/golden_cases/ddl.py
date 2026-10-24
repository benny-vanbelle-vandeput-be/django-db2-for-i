"""DDL goldens: CREATE TABLE per type rule, ALTER TABLE, DROP TABLE."""

from __future__ import annotations

from django.db.models import (
    NOT_PROVIDED,
    BigAutoField,
    BigIntegerField,
    CharField,
    Index,
    IntegerField,
)

from tests.golden_cases.base import (
    ACCOUNT,
    AUTHOR,
    BOOK,
    CONTACT,
    DEFAULTS,
    MEASURE,
    NODE,
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
    Schedule,
    Switch,
    Tag,
)


def _ddl(*models, foreign_keys: bool = False):
    def build(connection):
        features = connection.features
        saved = features.supports_foreign_keys
        features.supports_foreign_keys = foreign_keys
        try:
            with connection.schema_editor(collect_sql=True) as editor:
                for model in models:
                    editor.create_model(model)
        finally:
            features.supports_foreign_keys = saved
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _add_not_null_with_python_default(connection):
    """AddField of a NOT NULL column with a Python default (literal, then dropped)."""
    field = CharField(max_length=20, default="O'Brien")
    field.set_attributes_from_name("nickname")
    with connection.schema_editor(collect_sql=True) as editor:
        editor.add_field(Defaults, field)
    return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]


def _remove_field(model, name):
    """RemoveField: ALTER TABLE ... DROP COLUMN, the same on every Django version."""

    def build(connection):
        with connection.schema_editor(collect_sql=True) as editor:
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
        with connection.schema_editor(collect_sql=True) as editor:
            for old, new in changes:
                editor.alter_field(model, old(), new(), strict=True)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _rename_table_and_back(model, new_name):
    """RenameModel: RENAME TABLE, and back, so the later goldens find the table."""

    def build(connection):
        old_name = model._meta.db_table
        with connection.schema_editor(collect_sql=True) as editor:
            editor.alter_db_table(model, old_name, new_name)
            editor.alter_db_table(model, new_name, old_name)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _rename_index_and_back(model, fields, old_name, new_name):
    """RenameIndex: RENAME INDEX (can_rename_index), and back."""

    def build(connection):
        old, new = Index(fields=fields, name=old_name), Index(fields=fields, name=new_name)
        with connection.schema_editor(collect_sql=True) as editor:
            editor.rename_index(model, old, new)
            editor.rename_index(model, new, old)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


def _drop(model):
    def build(connection):
        with connection.schema_editor(collect_sql=True) as editor:
            editor.delete_model(model)
        return [(sql.removesuffix(";"), ()) for sql in editor.collected_sql]

    return build


CASES: tuple[Case, ...] = (
    # DDL types: identity columns, NVARCHAR, TIMESTAMP(6), TIME, BOOLEAN,
    # CHECK, UUID as CHAR(32), UNIQUE, indexes, NO ACTION foreign key.
    Case(AUTHOR, "create", _ddl(Author)),
    Case(BOOK, "create", _ddl(Book)),
    Case(NODE, "create", _ddl(Node, foreign_keys=True)),
    Case(TAG, "create", _ddl(Tag)),
    # Column DEFAULT literals, one per prepare_default() rule (no CAST).
    Case(DEFAULTS, "create", _ddl(Defaults)),
    # TextField and BinaryField: NCLOB and BLOB (1M, the default length).
    Case("ddl/create_document", "create", _ddl(Document)),
    # DurationField: BIGINT microseconds.
    Case(SCHEDULE, "create", _ddl(Schedule)),
    # Foreign keys to integer, CharField, UUID and key primary keys; an IP.
    Case("ddl/create_code", "create", _ddl(Code)),
    Case("ddl/create_profile", "create", _ddl(Profile)),
    Case("ddl/create_link", "create", _ddl(Link)),
    # A composite UNIQUE key, the target of a two-column ForeignObject.
    Case(ACCOUNT, "create", _ddl(Account)),
    Case(CONTACT, "create", _ddl(Contact)),
    # A nullable BOOLEAN column.
    Case(SWITCH, "create", _ddl(Switch)),
    # SMALLINT, DECIMAL(5, 2) and BIGINT columns (issue #69).
    Case(MEASURE, "create", _ddl(Measure)),
    # Fields from an abstract mixin and an abstract base: column order (#23).
    Case("ddl/create_article", "create", _ddl(Article)),
    Case(
        "ddl/add_field_not_null_default",
        "create",
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
        "ddl/rename_index",
        "alter",
        _rename_index_and_back(
            Book, ["title"], "testapp_book_title_c797b345", "testapp_book_title_idx"
        ),
        (BOOK,),
    ),
    # Identity changes: AutoField -> IntegerField drops the identity;
    # IntegerField -> AutoField adds it and restarts after MAX(); AutoField ->
    # BigAutoField widens it.
    Case(
        "ddl/alter_field_identity",
        "alter",
        _alter(
            Author,
            (lambda: _field(Author, "id"), lambda: _field(Author, "id", IntegerField)),
            (lambda: _field(Author, "id", IntegerField), lambda: _field(Author, "id")),
            (lambda: _field(Author, "id"), lambda: _field(Author, "id", BigAutoField)),
        ),
        (AUTHOR, BOOK),
    ),
    # The way back: narrowing and NOT NULL are cancelled by CPA32B2 (unverifiable.toml).
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
    # DROP COLUMN without CASCADE / RESTRICT on every Django version (probe 23).
    Case("ddl/remove_field", "drop", _remove_field(Defaults, "ratio"), (DEFAULTS,)),
    # DROP TABLE (cascades on Db2 for i).
    Case("ddl/drop_tag", "drop", _drop(Tag), (TAG,)),
)
