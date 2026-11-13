"""Renaming a column by copying it (OPTIONS["column_rename"] = "copy", #258 F), and
the record format warning (django_db2_for_i.W003). No server needed."""

import warnings

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import NotSupportedError, connection, models

from django_db2_for_i import column_copy
from django_db2_for_i.base import DatabaseWrapper
from django_db2_for_i.features import REASON_NO_COLUMN_RENAME, DatabaseFeatures
from django_db2_for_i.schema import RecordFormatChanged, record_format_change
from tests.testapp.models import Author

pytestmark = pytest.mark.offline


def wrapper(**options) -> DatabaseWrapper:
    settings = {**connection.settings_dict, "OPTIONS": {"capabilities": "7.5", **options}}
    return DatabaseWrapper(settings, alias="column_copy")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("N >= 0", '"NEW_N" >= 0'),
        ('"N" >= 0 AND NN < 5', '"NEW_N" >= 0 AND NN < 5'),
        ("N = 'N' OR N2 = 1", "\"NEW_N\" = 'N' OR N2 = 1"),
        ("LENGTH(N) > 1", 'LENGTH("NEW_N") > 1'),
        ("A.N > 1", 'A."NEW_N" > 1'),
        ("n > 1", '"NEW_N" > 1'),
    ],
)
def test_rename_in(text, expected) -> None:
    assert column_copy.rename_in(text, "N", "NEW_N") == expected


def test_the_option_defaults_to_refuse() -> None:
    assert wrapper().column_rename == "refuse"
    assert wrapper(column_rename="copy").column_rename == "copy"
    with pytest.raises(ImproperlyConfigured, match="column_rename"):
        _ = wrapper(column_rename="yes").column_rename


def test_rename_tests_run_only_with_the_option() -> None:
    renamed = DatabaseFeatures.expected_failures[REASON_NO_COLUMN_RENAME]
    refuse = wrapper().features
    copy = wrapper(column_rename="copy").features
    assert renamed <= refuse.django_test_expected_failures
    assert not renamed & copy.django_test_expected_failures
    assert REASON_NO_COLUMN_RENAME in refuse.django_test_skips
    assert REASON_NO_COLUMN_RENAME not in copy.django_test_skips


def _rename(db) -> list[str]:
    old = Author._meta.get_field("name")
    new = models.CharField(max_length=100, db_column="full_name")
    new.set_attributes_from_name("name")
    new.model = Author
    with db.schema_editor(collect_sql=True, atomic=False) as editor:
        editor.alter_field(Author, old, new, strict=True)
    assert db.connection is None, "collecting SQL must not connect"
    return editor.collected_sql


def test_without_the_option_a_rename_is_refused() -> None:
    with pytest.raises(NotSupportedError, match='column_rename"] = "copy"'):
        _rename(wrapper())


def test_collected_sql_of_a_copy() -> None:
    sql = _rename(wrapper(column_rename="copy"))
    assert sql[0].startswith("-- Db2 for i: the column is copied")
    assert sql[1:] == [
        'ALTER TABLE "TESTAPP_AUTHOR" ADD COLUMN "FULL_NAME" NVARCHAR(100) BEFORE "NAME";',
        'UPDATE "TESTAPP_AUTHOR" SET "FULL_NAME" = "NAME" WITH NC;',
        'ALTER TABLE "TESTAPP_AUTHOR" ALTER COLUMN "FULL_NAME" SET NOT NULL;',
        'ALTER TABLE "TESTAPP_AUTHOR" DROP COLUMN "NAME" RESTRICT;',
    ]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ('ALTER TABLE "T" ADD COLUMN "A" INTEGER', ('"T"', "ADD COLUMN")),
        (
            'ALTER TABLE "L"."T" ALTER COLUMN "A" SET DATA TYPE BIGINT DROP NOT NULL',
            ('"L"."T"', "ALTER COLUMN"),
        ),
        ("ALTER TABLE T DROP COLUMN A RESTRICT", ("T", "DROP COLUMN")),
        ('ALTER TABLE "T" ADD CONSTRAINT "C" UNIQUE ("A")', (None, "")),
        ('CREATE INDEX "I" ON "T" ("A")', (None, "")),
        ('UPDATE "T" SET "A" = 1', (None, "")),
    ],
)
def test_record_format_change(sql, expected) -> None:
    assert record_format_change(sql) == expected


def test_the_warning_names_each_changed_table_once(monkeypatch) -> None:
    db = wrapper()
    editor = db.schema_editor(atomic=False)
    for sql in (
        'CREATE TABLE "NEW" ("A" INTEGER)',
        'ALTER TABLE "NEW" ADD COLUMN "B" INTEGER',  # created by this editor: no warning
        'ALTER TABLE "T" ADD COLUMN "B" INTEGER',
        'ALTER TABLE "T" DROP COLUMN "C"',
        'ALTER TABLE "T" ADD CONSTRAINT "U" UNIQUE ("B")',
    ):
        editor._note_record_format(sql)

    def no_catalog():
        from django.db import DatabaseError

        raise DatabaseError("offline")

    monkeypatch.setattr(db, "cursor", no_catalog)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        editor._warn_record_formats()
    messages = [str(w.message) for w in caught if w.category is RecordFormatChanged]
    assert messages == [
        'django_db2_for_i.W003: the record format of "T" changed (ADD COLUMN, DROP COLUMN). '
        "RPG and CL programs compiled over it get a level check (CPF4131) until they are "
        "compiled again."
    ]
