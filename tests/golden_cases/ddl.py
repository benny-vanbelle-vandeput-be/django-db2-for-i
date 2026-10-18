"""DDL goldens: CREATE TABLE per type rule, ALTER TABLE, DROP TABLE."""

from __future__ import annotations

from django.db.models import (
    CharField,
)

from tests.golden_cases.base import AUTHOR, BOOK, DEFAULTS, NODE, TAG, Case
from tests.testapp.models import Author, Book, Defaults, Document, Node, Tag


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
    Case(
        "ddl/add_field_not_null_default",
        "create",
        _add_not_null_with_python_default,
        (DEFAULTS,),
    ),
    # DROP TABLE (cascades on Db2 for i).
    Case("ddl/drop_tag", "drop", _drop(Tag), (TAG,)),
)
