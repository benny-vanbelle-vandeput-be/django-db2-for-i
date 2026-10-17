"""DatabaseOperations: pure methods (no server needed)."""

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.core.management.color import no_style
from django.db import NotSupportedError, connection
from django.db.models import CharField, DateTimeField, UUIDField
from django.db.models.expressions import Col
from django.test.utils import override_settings
from django.utils import timezone

from django_db2_for_i.base import DatabaseWrapper
from django_db2_for_i.operations import children_first

ops = connection.ops


# --- last_insert_id ----------------------------------------------------------------


class IdentityCursor:
    def __init__(self, value):
        self.value = value
        self.sql = None

    def execute(self, sql):
        self.sql = sql

    def fetchone(self):
        return (self.value,)


def test_last_insert_id_converts_decimal_to_int() -> None:
    cursor = IdentityCursor(Decimal("42"))
    value = ops.last_insert_id(cursor, "basic_article", "id")
    assert value == 42
    assert type(value) is int
    assert cursor.sql == "SELECT IDENTITY_VAL_LOCAL() FROM SYSIBM.SYSDUMMY1"


def test_last_insert_id_none() -> None:
    assert ops.last_insert_id(IdentityCursor(None), "t", "id") is None


# --- Pagination --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("low", "high", "sql"),
    [
        (None, None, ""),
        (0, None, ""),
        (0, 10, "FETCH FIRST 10 ROWS ONLY"),
        (5, None, "OFFSET 5 ROWS"),
        (5, 15, "OFFSET 5 ROWS FETCH FIRST 10 ROWS ONLY"),
    ],
)
def test_limit_offset_sql(low, high, sql: str) -> None:
    assert ops.limit_offset_sql(low, high) == sql


def test_no_limit_value() -> None:
    assert ops.no_limit_value() is None


def test_limit_offset_needs_capability() -> None:
    settings_dict = dict(connection.settings_dict)
    settings_dict["OPTIONS"] = {"capabilities": {"profile": "7.5", "has_offset_fetch": False}}
    wrapper = DatabaseWrapper(settings_dict, alias="offline_test")
    with pytest.raises(NotSupportedError, match="has_offset_fetch"):
        wrapper.ops.limit_offset_sql(0, 10)


# --- Date/time ---------------------------------------------------------------------

AWARE = dt.datetime(2026, 10, 17, 15, 30, 0, 123456, tzinfo=dt.timezone(dt.timedelta(hours=2)))


def test_aware_datetime_is_stored_as_naive_utc() -> None:
    assert ops.adapt_datetimefield_value(AWARE) == dt.datetime(2026, 10, 17, 13, 30, 0, 123456)


def test_naive_datetime_is_passed_unchanged() -> None:
    naive = dt.datetime(2026, 10, 17, 13, 30)
    assert ops.adapt_datetimefield_value(naive) is naive


@override_settings(USE_TZ=False)
def test_aware_datetime_without_use_tz_raises() -> None:
    with pytest.raises(ValueError, match="USE_TZ is False"):
        ops.adapt_datetimefield_value(AWARE)


def test_none_values() -> None:
    assert ops.adapt_datetimefield_value(None) is None
    assert ops.adapt_datefield_value(None) is None
    assert ops.adapt_timefield_value(None) is None


def test_date_and_time_are_passed_as_objects() -> None:
    assert ops.adapt_datefield_value(dt.date(2026, 10, 17)) == dt.date(2026, 10, 17)
    assert ops.adapt_timefield_value(dt.time(13, 45, 30)) == dt.time(13, 45, 30)


def test_aware_time_raises() -> None:
    with pytest.raises(ValueError, match="timezone-aware times"):
        ops.adapt_timefield_value(dt.time(13, 45, tzinfo=dt.UTC))


def converters_for(field) -> list:
    return [converter for converter in ops.get_db_converters(Col("t", field))]


def test_datetime_read_back_as_aware_utc() -> None:
    (converter,) = converters_for(DateTimeField())
    value = converter(dt.datetime(2026, 10, 17, 13, 30), None, connection)
    assert value == dt.datetime(2026, 10, 17, 13, 30, tzinfo=dt.UTC)
    assert value.tzinfo is not None
    assert converter(None, None, connection) is None


@override_settings(USE_TZ=False)
def test_datetime_without_use_tz_has_no_converter() -> None:
    assert converters_for(DateTimeField()) == []


def test_uuid_converter() -> None:
    (converter,) = converters_for(UUIDField())
    value = uuid.uuid4()
    assert converter(value.hex, None, connection) == value
    assert converter(None, None, connection) is None


# --- Flush -------------------------------------------------------------------------


def flush(monkeypatch, tables, references=(), identities=None, **kwargs) -> list[str]:
    seen = {}

    def metadata(names):
        seen["names"] = names
        return set(references), identities or {}

    monkeypatch.setattr(ops, "_flush_metadata", metadata)
    statements = ops.sql_flush(no_style(), tables, **kwargs)
    assert seen["names"] == [table.upper() for table in tables]
    return statements


def test_sql_flush_empty_does_not_query(monkeypatch) -> None:
    monkeypatch.setattr(ops, "_flush_metadata", lambda names: pytest.fail("queried"))
    assert ops.sql_flush(no_style(), []) == []


def test_sql_flush_truncates_unreferenced_tables(monkeypatch) -> None:
    assert flush(monkeypatch, ["basic_article", "basic_tag"]) == [
        'TRUNCATE TABLE "BASIC_ARTICLE"',
        'TRUNCATE TABLE "BASIC_TAG"',
    ]


def test_sql_flush_restarts_identity_with_truncate(monkeypatch) -> None:
    assert flush(monkeypatch, ["basic_article"], reset_sequences=True) == [
        'TRUNCATE TABLE "BASIC_ARTICLE" RESTART IDENTITY'
    ]


def test_sql_flush_deletes_referenced_tables_after_children(monkeypatch) -> None:
    # c -> b -> a, plus an unrelated table d.
    references = {("C", "B"), ("B", "A")}
    assert flush(monkeypatch, ["a", "b", "c", "d"], references) == [
        'TRUNCATE TABLE "C"',
        'TRUNCATE TABLE "D"',
        'DELETE FROM "B"',
        'DELETE FROM "A"',
    ]


def test_sql_flush_restarts_identity_after_delete(monkeypatch) -> None:
    statements = flush(
        monkeypatch,
        ["parent", "child"],
        {("CHILD", "PARENT")},
        {"PARENT": ("ID", 1), "CHILD": ("ID", 1)},
        reset_sequences=True,
    )
    assert statements == [
        'TRUNCATE TABLE "CHILD" RESTART IDENTITY',
        'DELETE FROM "PARENT"',
        'ALTER TABLE "PARENT" ALTER COLUMN "ID" RESTART WITH 1',
    ]


def test_sql_flush_self_reference(monkeypatch) -> None:
    assert flush(monkeypatch, ["node"], {("NODE", "NODE")}) == ['DELETE FROM "NODE"']


def test_children_first_breaks_cycles() -> None:
    order = children_first({"A", "B"}, {("A", "B"), ("B", "A")})
    assert sorted(order) == ["A", "B"]


# --- TIME truncation and identity reset ----------------------------------------------


def test_time_microseconds_are_truncated() -> None:
    # Db2 for i TIME has no fractional seconds (docs/DECISIONS.md).
    assert ops.adapt_timefield_value(dt.time(13, 45, 30, 123456)) == dt.time(13, 45, 30)


def test_sequence_reset_sql(monkeypatch) -> None:
    from tests.testapp.models import Author, Book, Node, Tag

    queried = []

    def next_value(table, column):
        queried.append((table, column))
        return {"testapp_author": 1, "testapp_book": 101, "testapp_node": 7}[table]

    monkeypatch.setattr(ops, "_next_identity_value", next_value)
    statements = ops.sequence_reset_sql(no_style(), [Author, Book, Node, Tag])
    assert statements == [
        'ALTER TABLE "TESTAPP_AUTHOR" ALTER COLUMN "ID" RESTART WITH 1',
        'ALTER TABLE "TESTAPP_BOOK" ALTER COLUMN "ID" RESTART WITH 101',
        'ALTER TABLE "TESTAPP_NODE" ALTER COLUMN "ID" RESTART WITH 7',
    ]
    # Tag has a UUID primary key: no identity, no query.
    assert ("testapp_tag", "id") not in queried


# --- Identity restarts outside transactions (SQL0910) --------------------------------


@pytest.fixture
def wrapper(monkeypatch):
    """A fresh wrapper whose SQL execution and on_commit are recorded."""
    from django.db.backends.base.operations import BaseDatabaseOperations

    settings_dict = dict(connection.settings_dict)
    settings_dict["OPTIONS"] = dict(settings_dict["OPTIONS"])
    wrapper = DatabaseWrapper(settings_dict, alias="offline_test")
    wrapper.events = []
    wrapper.pending_on_commit = []
    monkeypatch.setattr(
        BaseDatabaseOperations,
        "execute_sql_flush",
        lambda self, sql_list: wrapper.events.append(("atomic flush", list(sql_list))),
    )
    monkeypatch.setattr(
        wrapper.ops, "_execute", lambda statements: wrapper.events.append(("execute", statements))
    )
    monkeypatch.setattr(wrapper, "on_commit", wrapper.pending_on_commit.append)
    monkeypatch.setattr(wrapper.ops, "_next_identity_value", lambda table, column: 8)
    return wrapper


FLUSH = [
    'TRUNCATE TABLE "CHILD" RESTART IDENTITY',
    'DELETE FROM "PARENT"',
    'ALTER TABLE "PARENT" ALTER COLUMN "ID" RESTART WITH 1',
]


def test_flush_restarts_after_its_atomic_block(wrapper) -> None:
    wrapper.ops.execute_sql_flush(FLUSH)
    # Data statements in Django's atomic block, then the restart, in that order.
    assert wrapper.events == [("atomic flush", FLUSH[:2]), ("execute", FLUSH[2:])]
    assert wrapper.pending_on_commit == []


def test_flush_in_outer_atomic_block_defers_restarts(wrapper) -> None:
    wrapper.in_atomic_block = True
    wrapper.ops.execute_sql_flush(FLUSH)
    assert wrapper.events == [("atomic flush", FLUSH[:2])]
    (callback,) = wrapper.pending_on_commit
    callback()  # as on commit
    assert wrapper.events[-1] == ("execute", FLUSH[2:])


def test_flush_without_restarts_registers_nothing(wrapper) -> None:
    wrapper.in_atomic_block = True
    wrapper.ops.execute_sql_flush(FLUSH[:2])
    assert wrapper.events == [("atomic flush", FLUSH[:2])]
    assert wrapper.pending_on_commit == []


def test_sequence_reset_outside_atomic_returns_sql(wrapper) -> None:
    from tests.testapp.models import Author

    assert wrapper.ops.sequence_reset_sql(no_style(), [Author]) == [
        'ALTER TABLE "TESTAPP_AUTHOR" ALTER COLUMN "ID" RESTART WITH 8'
    ]
    assert wrapper.pending_on_commit == []


def test_sequence_reset_in_atomic_block_is_deferred(wrapper, monkeypatch) -> None:
    from tests.testapp.models import Author

    wrapper.in_atomic_block = True
    queried = []
    monkeypatch.setattr(
        wrapper.ops, "_next_identity_value", lambda table, column: queried.append(table) or 8
    )
    assert wrapper.ops.sequence_reset_sql(no_style(), [Author]) == []
    assert queried == []  # MAX(pk) is computed only after the commit
    (callback,) = wrapper.pending_on_commit
    callback()
    assert queried == ["testapp_author"]
    assert wrapper.events == [
        ("execute", ['ALTER TABLE "TESTAPP_AUTHOR" ALTER COLUMN "ID" RESTART WITH 8'])
    ]


def test_deferred_flush_restart_is_logged(wrapper, caplog) -> None:
    wrapper.in_atomic_block = True
    with caplog.at_level("DEBUG", logger="django_db2_for_i"):
        wrapper.ops.execute_sql_flush(FLUSH)
    assert "Identity restart deferred until commit (SQL0910)" in caplog.text
    assert 'ALTER TABLE "PARENT" ALTER COLUMN "ID" RESTART WITH 1' in caplog.text


def test_deferred_sequence_reset_is_logged(wrapper, caplog) -> None:
    from tests.testapp.models import Author

    wrapper.in_atomic_block = True
    with caplog.at_level("DEBUG", logger="django_db2_for_i"):
        wrapper.ops.sequence_reset_sql(no_style(), [Author])
    assert "sequence reset for testapp_author" in caplog.text


def test_immediate_restart_is_not_logged(wrapper, caplog) -> None:
    with caplog.at_level("DEBUG", logger="django_db2_for_i"):
        wrapper.ops.execute_sql_flush(FLUSH)
    assert "deferred" not in caplog.text


# --- Case-insensitive lookups ----------------------------------------------------------


@pytest.mark.parametrize("lookup", ["iexact", "icontains", "istartswith", "iendswith"])
def test_case_insensitive_lookups_uppercase_the_column(lookup) -> None:
    from tests.testapp.models import Author

    sql, _params = (
        Author.objects.filter(**{f"name__{lookup}": "Ada"}).query.get_compiler("default").as_sql()
    )
    assert 'UPPER("TESTAPP_AUTHOR"."NAME")' in sql
    assert "UPPER(%s)" in sql


@pytest.mark.parametrize("lookup", ["exact", "contains", "startswith", "gt"])
def test_case_sensitive_lookups_leave_the_column_alone(lookup) -> None:
    assert ops.lookup_cast(lookup) == "%s"


# --- Savepoints ------------------------------------------------------------------------


def test_savepoint_sql() -> None:
    sid = "s140234567890123_x1"
    assert ops.savepoint_create_sql(sid) == (
        'SAVEPOINT "S140234567890123_X1" ON ROLLBACK RETAIN CURSORS'
    )
    assert ops.savepoint_commit_sql(sid) == 'RELEASE SAVEPOINT "S140234567890123_X1"'
    assert ops.savepoint_rollback_sql(sid) == 'ROLLBACK TO SAVEPOINT "S140234567890123_X1"'


# --- Extracting date/time parts --------------------------------------------------------


@pytest.mark.parametrize(
    ("lookup", "sql"),
    [
        ("year", "YEAR(col)"),
        ("iso_year", "INTEGER(VARCHAR_FORMAT(col, 'IYYY'))"),
        ("quarter", "QUARTER(col)"),
        ("month", "MONTH(col)"),
        ("week", "WEEK_ISO(col)"),
        ("week_day", "DAYOFWEEK(col)"),
        ("iso_week_day", "DAYOFWEEK_ISO(col)"),
        ("day", "DAY(col)"),
        ("hour", "HOUR(col)"),
        ("minute", "MINUTE(col)"),
        ("second", "SECOND(col)"),
    ],
)
def test_datetime_extract_sql(lookup, sql) -> None:
    assert ops.datetime_extract_sql(lookup, "col", ("p",), None) == (sql, ("p",))


def test_date_and_time_extract_only_their_parts() -> None:
    assert ops.date_extract_sql("week_day", "col", ()) == ("DAYOFWEEK(col)", ())
    assert ops.time_extract_sql("second", "col", ()) == ("SECOND(col)", ())
    with pytest.raises(ValueError, match="Invalid lookup type"):
        ops.date_extract_sql("hour", "col", ())
    with pytest.raises(ValueError, match="Invalid lookup type"):
        ops.time_extract_sql("year", "col", ())
    with pytest.raises(ValueError, match="Invalid lookup type"):
        ops.datetime_extract_sql("epoch", "col", (), None)


def test_extract_in_the_connection_time_zone_needs_no_conversion() -> None:
    assert connection.timezone_name == "UTC"
    assert ops.datetime_extract_sql("hour", "col", (), "UTC") == ("HOUR(col)", ())


def test_extract_in_another_time_zone_is_not_supported() -> None:
    with pytest.raises(NotSupportedError, match=r"'UTC'.*'Europe/Brussels'"):
        ops.datetime_extract_sql("hour", "col", (), "Europe/Brussels")


def test_extract_uses_the_databases_time_zone_setting() -> None:
    """DATABASES TIME_ZONE (existing tables in local time) is the stored zone."""
    wrapper = DatabaseWrapper(
        {**connection.settings_dict, "TIME_ZONE": "Europe/Brussels"}, alias="offline_test"
    )
    assert wrapper.timezone_name == "Europe/Brussels"
    assert wrapper.ops.datetime_extract_sql("day", "col", (), "Europe/Brussels") == (
        "DAY(col)",
        (),
    )
    with pytest.raises(NotSupportedError, match=r"'Europe/Brussels'.*'UTC'"):
        wrapper.ops.datetime_extract_sql("day", "col", (), "UTC")


def test_week_day_lookup_with_a_current_time_zone_other_than_the_database() -> None:
    from tests.testapp.models import Book

    with timezone.override("Europe/Brussels"), pytest.raises(NotSupportedError):
        Book.objects.filter(published__week_day=1).query.get_compiler("default").as_sql()


def test_cast_char_field_without_max_length() -> None:
    assert connection.ops.cast_char_field_without_max_length == "NVARCHAR(16370)"
    assert CharField().cast_db_type(connection) == "NVARCHAR(16370)"
    assert CharField(max_length=20).cast_db_type(connection) == "NVARCHAR(20)"
