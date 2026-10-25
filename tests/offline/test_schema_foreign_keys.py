"""Foreign key DDL collected with schema_editor(collect_sql=True) (no server needed).

``supports_foreign_keys`` is off until Django's test suite backs it; these
tests switch it on to check the DDL the schema editor would write. Foreign
keys are separate ALTER TABLE ... ADD CONSTRAINT statements
(``can_create_inline_fk`` stays off) without an ON DELETE clause: Django's
on_delete runs in Python, and Db2 for i's default is NO ACTION.
"""

import pytest
from django.db import connection, models

from tests.testapp.models import Author, Tag

ADD_COLUMN = 'ALTER TABLE "TESTAPP_TAG" ADD COLUMN "AUTHOR_ID" INTEGER;'
ADD_CONSTRAINT = (
    'ALTER TABLE "TESTAPP_TAG" ADD CONSTRAINT '
    '"TESTAPP_TAG_AUTHOR_ID_C6F86C93_FK_TESTAPP_AUTHOR_ID" '
    'FOREIGN KEY ("AUTHOR_ID") REFERENCES "TESTAPP_AUTHOR" ("ID");'
)
CREATE_INDEX = 'CREATE INDEX "TESTAPP_TAG_AUTHOR_ID_C6F86C93" ON "TESTAPP_TAG" ("AUTHOR_ID");'


@pytest.fixture(autouse=True)
def _foreign_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection.features, "supports_foreign_keys", True)


def add_field(model, field, name) -> list[str]:
    field.set_attributes_from_name(name)
    with connection.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.add_field(model, field)
    assert connection.connection is None, "collecting SQL must not connect"
    return editor.collected_sql


@pytest.mark.parametrize(
    "on_delete",
    [models.CASCADE, models.PROTECT, models.RESTRICT, models.SET_NULL, models.DO_NOTHING],
    ids=["CASCADE", "PROTECT", "RESTRICT", "SET_NULL", "DO_NOTHING"],
)
def test_python_on_delete_writes_the_same_constraint(on_delete) -> None:
    """Every Python-level on_delete gives the same NO ACTION constraint."""
    sql = add_field(Tag, models.ForeignKey(Author, on_delete, null=True), "author")
    assert sql == [ADD_COLUMN, ADD_CONSTRAINT, CREATE_INDEX]
    assert not any("ON DELETE" in statement or "RESTRICT" in statement for statement in sql)


def test_db_constraint_false_writes_no_constraint() -> None:
    """db_constraint=False: the column and Django's index, no constraint."""
    field = models.ForeignKey(Author, models.DO_NOTHING, null=True, db_constraint=False)
    assert add_field(Tag, field, "author") == [ADD_COLUMN, CREATE_INDEX]


def test_foreign_key_to_a_unique_field() -> None:
    """to_field: the key references the UNIQUE column, typed like it."""
    field = models.ForeignKey(Tag, models.CASCADE, null=True, to_field="label")
    sql = add_field(Author, field, "tag")
    assert sql[0] == 'ALTER TABLE "TESTAPP_AUTHOR" ADD COLUMN "TAG_ID" NVARCHAR(50);'
    assert sql[1].endswith('FOREIGN KEY ("TAG_ID") REFERENCES "TESTAPP_TAG" ("LABEL");')


def test_one_to_one_is_unique_without_an_extra_index() -> None:
    """OneToOneField: UNIQUE on the column, the constraint, no separate index."""
    sql = add_field(Tag, models.OneToOneField(Author, models.CASCADE, null=True), "author")
    assert sql == [ADD_COLUMN.replace("INTEGER;", "INTEGER UNIQUE;"), ADD_CONSTRAINT]


def test_foreign_keys_stay_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the flag no constraint is written, only the column and the index."""
    monkeypatch.setattr(connection.features, "supports_foreign_keys", False)
    sql = add_field(Tag, models.ForeignKey(Author, models.CASCADE, null=True), "author")
    assert sql == [ADD_COLUMN, CREATE_INDEX]
