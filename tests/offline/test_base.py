"""DatabaseWrapper, placeholder conversion and features (no server needed)."""

import django.db
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, connections

from django_db2_for_i.base import DatabaseWrapper, FormatStyleCursor, convert_placeholders
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


@pytest.mark.parametrize("method", ["execute", "executemany"])
def test_dict_params_are_not_supported(method: str) -> None:
    cursor = FormatStyleCursor(RecordingCursor())
    params = {"a": 1}
    with pytest.raises(Database.NotSupportedError, match="pyformat"):
        if method == "execute":
            cursor.execute("SELECT %(a)s", params)
        else:
            cursor.executemany("SELECT %(a)s", [params])


def test_dict_params_become_django_not_supported_error() -> None:
    cursor = FormatStyleCursor(RecordingCursor())
    with (
        pytest.raises(django.db.NotSupportedError, match="pyformat"),
        connection.wrap_database_errors,
    ):
        cursor.execute("SELECT %(a)s", {"a": 1})


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
    assert features.can_rollback_ddl is False
    assert features.uses_savepoints is True
    assert features.can_release_savepoints is True
    assert features.supports_timezones is False
    assert features.supports_paramstyle_pyformat is False
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
    assert set(cls.django_test_skips) == {features.REASON_DURATIONS_DEFERRED}
    # Each entry is one test id, never a whole class.
    for test_ids in cls.django_test_skips.values():
        assert all(test_id.count(".") >= 3 and ".test_" in test_id for test_id in test_ids)


def test_expected_failures_are_grouped_by_fixed_reasons() -> None:
    from django_db2_for_i import features

    cls = features.DatabaseFeatures
    assert set(cls.expected_failures) == {
        features.REASON_TIME_FRACTIONS,
        features.REASON_IDENTITY_RESTART_DEFERRED,
        features.REASON_UNTYPED_NULL,
        features.REASON_TYPED_PARAMETER_MARKERS,
        features.REASON_UNTYPED_RAW_SQL_PARAMETER,
    }
    # Each entry is one test id, never a whole class.
    for test_ids in cls.expected_failures.values():
        assert all(test_id.count(".") >= 3 and ".test_" in test_id for test_id in test_ids)
    assert features.REASON_IDENTITY_RESTART_DEFERRED == (
        "identity restart deferred in TestCase (SQL0910)"
    )
    assert cls.django_test_expected_failures == set().union(*cls.expected_failures.values())


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
