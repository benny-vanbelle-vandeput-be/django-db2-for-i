"""DatabaseWrapper, placeholder conversion and features (no server needed)."""

import django.db
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, connections

from django_db2_for_i.base import (
    DatabaseWrapper,
    FormatStyleCursor,
    convert_placeholders,
    strip_statement_end,
)
from django_db2_for_i.drivers import base as Database


def make_wrapper(**overrides) -> DatabaseWrapper:
    settings_dict = dict(connections["default"].settings_dict)
    settings_dict["OPTIONS"] = dict(settings_dict["OPTIONS"])
    options = overrides.pop("OPTIONS", None)
    if options is not None:
        settings_dict["OPTIONS"] = options
    settings_dict.update(overrides)
    return DatabaseWrapper(settings_dict, alias="offline_test")


# --- Placeholder conversion -------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT %s FROM T WHERE A = %s", "SELECT ? FROM T WHERE A = ?"),
        ("SELECT '100%%' FROM T WHERE A = %s", "SELECT '100%' FROM T WHERE A = ?"),
        ("WHERE A LIKE '%%x%%' AND B = %s", "WHERE A LIKE '%x%' AND B = ?"),
        # "%%s" is a literal "%s", not a placeholder.
        ("SELECT '%%s', %s", "SELECT '%s', ?"),
        ("SELECT '%%%s'", "SELECT '%?'"),
        ("SELECT 1", "SELECT 1"),
        # Other % sequences are not Django's and are left alone.
        ("SELECT '%d'", "SELECT '%d'"),
    ],
)
def test_convert_placeholders(sql: str, expected: str) -> None:
    assert convert_placeholders(sql) == expected


class RecordingCursor:
    def __init__(self):
        self.calls: list[tuple] = []
        self.closed = False

    def execute(self, *args):
        self.calls.append(("execute", *args))

    def executemany(self, *args):
        self.calls.append(("executemany", *args))

    def close(self):
        self.closed = True


def test_execute_without_params_sends_sql_unchanged() -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).execute("SELECT '100%' FROM T WHERE A LIKE '%%s'")
    assert raw.calls == [("execute", "SELECT '100%' FROM T WHERE A LIKE '%%s'")]


def test_execute_with_params_converts() -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).execute("SELECT '100%%' FROM T WHERE A = %s", [1])
    assert raw.calls == [("execute", "SELECT '100%' FROM T WHERE A = ?", [1])]


def test_execute_with_empty_params_converts() -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).execute("SELECT '100%%' FROM T", [])
    assert raw.calls == [("execute", "SELECT '100%' FROM T", [])]


def test_executemany_converts() -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).executemany("INSERT INTO T VALUES (%s)", iter([[1], [2]]))
    assert raw.calls == [("executemany", "INSERT INTO T VALUES (?)", [[1], [2]])]


def test_executemany_without_rows_does_nothing() -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).executemany("INSERT INTO T VALUES (%s)", [])
    assert raw.calls == []


def test_execute_with_dict_params_converts() -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).execute(
        "SELECT '100%%' FROM T WHERE A = %(a)s AND B = %(b)s OR C = %(a)s", {"b": 2, "a": 1}
    )
    assert raw.calls == [
        ("execute", "SELECT '100%' FROM T WHERE A = ? AND B = ? OR C = ?", [1, 2, 1])
    ]


def test_executemany_with_dict_params_converts() -> None:
    raw = RecordingCursor()
    rows = iter([{"a": 1, "b": 2}, {"b": 4, "a": 3}])
    FormatStyleCursor(raw).executemany("INSERT INTO T VALUES (%(a)s, %(b)s)", rows)
    assert raw.calls == [("executemany", "INSERT INTO T VALUES (?, ?)", [[1, 2], [3, 4]])]


def test_dict_params_with_a_missing_name() -> None:
    cursor = FormatStyleCursor(RecordingCursor())
    with pytest.raises(Database.ProgrammingError, match=r"%\(b\)s"):
        cursor.execute("SELECT %(a)s, %(b)s", {"a": 1})


def test_dict_params_with_a_plain_placeholder() -> None:
    cursor = FormatStyleCursor(RecordingCursor())
    with pytest.raises(Database.ProgrammingError, match="cannot be mixed"):
        cursor.execute("SELECT %(a)s, %s", {"a": 1})


def test_dict_params_become_django_programming_error() -> None:
    cursor = FormatStyleCursor(RecordingCursor())
    with (
        pytest.raises(django.db.ProgrammingError, match="cannot be mixed"),
        connection.wrap_database_errors,
    ):
        cursor.execute("SELECT %(a)s, %s", {"a": 1})


def test_last_executed_query_with_dict_params() -> None:
    sql = "INSERT INTO T (A, B) VALUES (%(root)s, %(root2)s)"
    assert connection.ops.last_executed_query(None, sql, {"root": 2, "root2": "x'y"}) == (
        "INSERT INTO T (A, B) VALUES (2, 'x''y')"
    )


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1;", "SELECT 1"),
        ("SELECT 1; ", "SELECT 1"),
        ("SELECT 1;\n", "SELECT 1"),
        # Only one is removed: Db2 for i still rejects the rest (SQL0104).
        ("SELECT 1;;", "SELECT 1;"),
        # A ";" inside a string literal is not the statement's end.
        ("SELECT ';' FROM T", "SELECT ';' FROM T"),
        ("SELECT 'a;' FROM T WHERE B = 'x;'", "SELECT 'a;' FROM T WHERE B = 'x;'"),
        ("SELECT ';' FROM T;", "SELECT ';' FROM T"),
        # Without a ";" the SQL stays as it is, trailing whitespace included.
        ("SELECT 1 ", "SELECT 1 "),
    ],
)
def test_strip_statement_end(sql: str, expected: str) -> None:
    assert strip_statement_end(sql) == expected


@pytest.mark.parametrize("params", [None, [1]])
def test_execute_strips_one_trailing_semicolon(params) -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).execute("SELECT %s; " if params else "SELECT 1;", params)
    sql = raw.calls[0][1]
    assert sql == ("SELECT ?" if params else "SELECT 1")


def test_executemany_strips_one_trailing_semicolon() -> None:
    raw = RecordingCursor()
    FormatStyleCursor(raw).executemany("INSERT INTO T VALUES (%s);", [[1], [2]])
    assert raw.calls == [("executemany", "INSERT INTO T VALUES (?)", [[1], [2]])]


def test_cursor_context_manager_closes() -> None:
    raw = RecordingCursor()
    with FormatStyleCursor(raw) as cursor:
        cursor.execute("SELECT 1")
    assert raw.closed


# --- Connection parameters -----------------------------------------------------


def test_connection_params() -> None:
    params = make_wrapper(NAME="djtest").get_connection_params()["params"]
    assert params == Database.ConnectionParams(
        host="offline.invalid",
        user="DJUSER",
        password="offline-not-a-password",
        default_schema="DJTEST",
        ssl=True,
        isolation_level="*CS",
        login_timeout=10,
        attributes={},
    )


def test_connection_params_from_options() -> None:
    options = {
        "capabilities": "7.5",
        "ssl": False,
        "isolation_level": "read committed",
        "login_timeout": 3,
        "driver_attributes": {"XDYNAMIC": "1"},
    }
    params = make_wrapper(OPTIONS=options).get_connection_params()["params"]
    assert params.ssl is False
    assert params.isolation_level == "read committed"
    assert params.login_timeout == 3
    assert params.attributes == {"XDYNAMIC": "1"}


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"HOST": ""}, "HOST is required"),
        ({"PORT": "8471"}, "PORT is not supported"),
        ({"NAME": ""}, "NAME .* is required"),
        ({"OPTIONS": {"sll": True}}, "Unknown OPTIONS .*: sll"),
        ({"OPTIONS": {"isolation_level": "snapshot"}}, "unknown isolation level"),
    ],
)
def test_connection_params_invalid(overrides: dict, message: str) -> None:
    with pytest.raises(ImproperlyConfigured, match=message) as info:
        make_wrapper(**overrides).get_connection_params()
    assert "offline-not-a-password" not in str(info.value)


def test_unknown_driver() -> None:
    with pytest.raises(ImproperlyConfigured, match="unknown driver 'ibm_db'"):
        _ = make_wrapper(OPTIONS={"driver": "ibm_db"}).driver


def test_invalid_capabilities_option() -> None:
    with pytest.raises(ImproperlyConfigured, match="unknown capability profile"):
        _ = make_wrapper(OPTIONS={"capabilities": "7.4"}).capabilities


# --- Capabilities and features without a connection ---------------------------------


def test_capabilities_from_profile_without_connection() -> None:
    wrapper = make_wrapper()
    assert wrapper.capabilities.source == "profile 7.5"
    assert wrapper.get_database_version() == (7, 5)
    assert wrapper.connection is None


def test_capabilities_without_boolean_type_are_refused() -> None:
    wrapper = make_wrapper(OPTIONS={"capabilities": {"profile": "7.5", "has_boolean_type": False}})
    with pytest.raises(django.db.NotSupportedError, match="BOOLEAN"):
        _ = wrapper.capabilities


def test_features() -> None:
    features = make_wrapper().features
    assert features.supports_transactions is True
    assert features.can_rollback_ddl is True
    assert features.uses_savepoints is True
    assert features.can_release_savepoints is True
    assert features.supports_timezones is False
    assert features.supports_paramstyle_pyformat is True
    assert features.has_native_boolean_field is True
    assert features.minimum_database_version == (7, 5)


def test_supports_transactions_never_probes() -> None:
    # Django's default is a cached_property that creates a table.
    assert "supports_transactions" in vars(type(make_wrapper().features))
    assert isinstance(type(make_wrapper().features).supports_transactions, bool)


@pytest.mark.parametrize(
    ("field", "data_type"),
    [
        ("AutoField", "INTEGER GENERATED BY DEFAULT AS IDENTITY"),
        ("BigAutoField", "BIGINT GENERATED BY DEFAULT AS IDENTITY"),
        ("SmallAutoField", "SMALLINT GENERATED BY DEFAULT AS IDENTITY"),
        ("CharField", "NVARCHAR(%(max_length)s)"),
        ("BooleanField", "BOOLEAN"),
        ("DateTimeField", "TIMESTAMP(6)"),
    ],
)
def test_data_types(field: str, data_type: str) -> None:
    assert make_wrapper().data_types[field] == data_type


# --- Identifiers ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "quoted"),
    [
        ("basic_article", '"BASIC_ARTICLE"'),
        ("MixedCase", '"MIXEDCASE"'),
        ('"ALREADY"', '"ALREADY"'),
        ('we"ird', '"WE""IRD"'),
    ],
)
def test_quote_name(name: str, quoted: str) -> None:
    assert make_wrapper().ops.quote_name(name) == quoted


def test_quote_name_truncates_to_max_name_length() -> None:
    quoted = make_wrapper().ops.quote_name("x" * 200)
    assert len(quoted) == 128 + 2


def test_identifier_converter() -> None:
    assert make_wrapper().introspection.identifier_converter("BASIC_ARTICLE") == "basic_article"


def test_skips_are_grouped_by_fixed_reasons() -> None:
    from django_db2_for_i import features

    cls = features.DatabaseFeatures
    assert set(cls.django_test_skips) == {
        features.REASON_NO_COLUMN_RENAME,
        features.REASON_NO_SUCH_FUNCTION,
        features.REASON_TRUNC_NULL_ZONEINFO,
    }
    # Each entry is one test id, never a whole class.
    for test_ids in cls.django_test_skips.values():
        assert all(test_id.count(".") >= 3 and ".test_" in test_id for test_id in test_ids)


def test_skips_are_the_same_on_every_django_version() -> None:
    """Skips are not filtered per version (compat), except the Trunc NULL test
    of 5.2 and 6.0 (an inherited test, features.py), and a test is never both
    skipped and an expected failure."""
    from django_db2_for_i import compat, features

    cls = features.DatabaseFeatures
    skipped = set().union(*cls.django_test_skips.values()) - set(compat.TRUNC_NULL_FAILING)
    assert skipped == {
        "schema.tests.SchemaTests.test_m2m_repoint",
        "schema.tests.SchemaTests.test_m2m_repoint_custom",
        "schema.tests.SchemaTests.test_m2m_repoint_inherited",
        "db_functions.text.test_reverse.ReverseTests.test_basic",
        "db_functions.text.test_reverse.ReverseTests.test_expressions",
        "db_functions.text.test_reverse.ReverseTests.test_null",
        "db_functions.text.test_reverse.ReverseTests.test_transform",
        "db_functions.text.test_sha224.SHA224Tests.test_basic",
        "db_functions.text.test_sha224.SHA224Tests.test_transform",
        "db_functions.text.test_sha384.SHA384Tests.test_basic",
        "db_functions.text.test_sha384.SHA384Tests.test_transform",
    }
    assert not skipped & set().union(*cls.expected_failures.values())


def test_expected_failures_are_grouped_by_fixed_reasons() -> None:
    from django_db2_for_i import features

    cls = features.DatabaseFeatures
    assert set(cls.expected_failures) == {
        features.REASON_TIME_FRACTIONS,
        features.REASON_IDENTITY_RESTART_DEFERRED,
        features.REASON_UNTYPED_NULL,
        features.REASON_TYPED_PARAMETER_MARKERS,
        features.REASON_UNTYPED_RAW_SQL_PARAMETER,
        features.REASON_PENDING_ROW_CHANGES,
        features.REASON_NO_COLUMN_RENAME,
        features.REASON_POSTGRESQL_LIKE_INDEXES,
        features.REASON_TYPE_NOT_IN_PLACE,
        features.REASON_CHECK_LIKE_COLUMN_PATTERN,
        features.REASON_FINAL_TABLE_NOT_RETURNING,
        features.REASON_LOWERCASE_NAME_IN_SQL,
        features.REASON_MERGE_RETURNS_NO_ROWS,
        features.REASON_TIME_ZONE_CONVERSION,
        features.REASON_EXTRACT_IN_SQL,
        features.REASON_TRUNC_KIND_REFUSED,
        features.REASON_NO_JSON_CHECK,
        features.REASON_JSON_KEY_ORDER_AS_TEXT,
        features.REASON_JSON_KEY_DOUBLE_QUOTE,
        features.REASON_JSON_IN_CHECK_OR_INDEX,
        features.REASON_READERS_WAIT_FOR_ROW_LOCKS,
        features.REASON_JOIN_LOCKED_WITHOUT_FOR_UPDATE,
        features.REASON_FOR_UPDATE_TEXT,
    }
    # Each entry is one test id, never a whole class.
    for test_ids in cls.expected_failures.values():
        assert all(test_id.count(".") >= 3 and ".test_" in test_id for test_id in test_ids)
    assert features.REASON_IDENTITY_RESTART_DEFERRED == (
        "identity restart deferred in TestCase (SQL0910)"
    )
    from django_db2_for_i import compat

    everything = set().union(*cls.expected_failures.values())
    assert cls.django_test_expected_failures == everything - compat.PASSING_ON_THIS_VERSION
    # The per-version exceptions are expected failures of the other versions.
    assert compat.PASSING_ON_THIS_VERSION.issubset(everything)


def test_table_list_leaves_out_system_catalog_views() -> None:
    executed = []

    class Cursor:
        def execute(self, sql, params=None):
            executed.append(sql)

        def fetchall(self):
            return [("TESTAPP_AUTHOR", "T")]

    tables = make_wrapper().introspection.get_table_list(Cursor())
    assert [t.name for t in tables] == ["testapp_author"]
    assert "SYSTEM_TABLE = 'N'" in executed[0]


# --- Ending a transaction that holds a LOCK TABLE lock (#162) ----------------------


class FakeDriverConnection:
    """Records the driver's commit / rollback and the statements of its cursors."""

    def __init__(self, fail: str = ""):
        self.calls: list[str] = []
        self.fail = fail

    def commit(self):
        self.calls.append("driver commit")

    def rollback(self):
        self.calls.append("driver rollback")

    def close(self):
        self.calls.append("close")

    def cursor(self):
        conn = self

        class Cursor:
            def execute(self, sql, params=None):
                conn.calls.append(f"SQL {sql}")
                if sql == conn.fail:
                    raise Database.OperationalError(f"{sql} failed")

            def close(self):
                pass

        return Cursor()


def wrapper_with(fake, held: bool) -> DatabaseWrapper:
    wrapper = make_wrapper()
    wrapper.connection = fake
    wrapper._table_lock_held = held
    return wrapper


def test_without_a_table_lock_the_driver_ends_the_transaction() -> None:
    fake = FakeDriverConnection()
    wrapper = wrapper_with(fake, held=False)
    wrapper._commit()
    wrapper._rollback()
    assert fake.calls == ["driver commit", "driver rollback"]


@pytest.mark.parametrize("method", ["_commit", "_rollback"])
def test_a_table_lock_ends_with_the_sql_statement(method) -> None:
    """The driver's commit and rollback keep a LOCK TABLE lock; the SQL statements
    release it (probe lib_lock_table --followup)."""
    fake = FakeDriverConnection()
    wrapper = wrapper_with(fake, held=True)
    getattr(wrapper, method)()
    assert fake.calls == ["SQL COMMIT" if method == "_commit" else "SQL ROLLBACK"]
    assert wrapper._table_lock_held is False
    getattr(wrapper, method)()  # the next transaction: the driver again
    assert fake.calls[-1].startswith("driver")


def test_a_failed_sql_commit_keeps_the_flag_for_the_rollback() -> None:
    fake = FakeDriverConnection(fail="COMMIT")
    wrapper = wrapper_with(fake, held=True)
    with pytest.raises(django.db.OperationalError):
        wrapper._commit()
    assert wrapper._table_lock_held is True
    wrapper._rollback()
    assert fake.calls == ["SQL COMMIT", "SQL ROLLBACK"]
    assert wrapper._table_lock_held is False


def test_a_failed_sql_rollback_closes_the_connection() -> None:
    """The driver's rollback would keep the lock (#162); closing releases it."""
    fake = FakeDriverConnection(fail="ROLLBACK")
    wrapper = wrapper_with(fake, held=True)
    with pytest.raises(django.db.OperationalError):
        wrapper._rollback()
    assert fake.calls == ["SQL ROLLBACK", "close"]
    assert "driver rollback" not in fake.calls
    assert wrapper.connection is None  # Django connects again on the next query
    assert wrapper._table_lock_held is False


def test_a_savepoint_rollback_keeps_the_flag() -> None:
    """An atomic() inside another (a TestCase's test): the unit of work goes on."""
    fake = FakeDriverConnection()
    wrapper = wrapper_with(fake, held=True)
    wrapper.cursor = lambda: FormatStyleCursor(fake.cursor())
    wrapper._savepoint_rollback("S1")
    assert wrapper._table_lock_held is True
    assert not any(call.startswith("driver") for call in fake.calls)


def test_close_clears_the_flag() -> None:
    fake = FakeDriverConnection()
    wrapper = wrapper_with(fake, held=True)
    wrapper._close()
    assert wrapper._table_lock_held is False


def test_a_new_connection_clears_the_flag(monkeypatch) -> None:
    wrapper = make_wrapper()
    wrapper._table_lock_held = True
    monkeypatch.setattr(wrapper.driver, "connect", lambda params, autocommit: object())
    wrapper.get_new_connection(wrapper.get_connection_params())
    assert wrapper._table_lock_held is False
