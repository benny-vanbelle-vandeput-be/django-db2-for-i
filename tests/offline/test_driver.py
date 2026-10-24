"""Driver layer: connection string, error mapping and redaction (no server needed).

The driver messages below are real ones from the PUB400 probes
(docs/IBMI_NOTES.md), with user and library names replaced.
"""

import pyodbc
import pytest

from django_db2_for_i.drivers import base
from django_db2_for_i.drivers import pyodbc as pyodbc_driver
from django_db2_for_i.drivers.pyodbc import connection_string, translate_error

PASSWORD = "s3cr;et}pw"


def params(**overrides) -> base.ConnectionParams:
    values = {
        "host": "ibmi.example.com",
        "user": "DJUSER",
        "password": PASSWORD,
        "default_schema": "DJTEST",
    }
    return base.ConnectionParams(**(values | overrides))


def keywords(dsn: str) -> dict[str, str]:
    """Split a connection string whose only braced value with ';' is PWD."""
    head, _, tail = dsn.partition(";PWD=")
    pwd, _, rest = tail.partition("};")
    pairs = [item.split("=", 1) for item in f"{head};{rest}".split(";")]
    return {key: value for key, value in pairs} | {"PWD": pwd + "}"}


# --- Connection string ------------------------------------------------------


def test_connection_string_defaults() -> None:
    kw = keywords(connection_string(params()))
    assert kw == {
        "DRIVER": "{IBM i Access ODBC Driver}",
        "SYSTEM": "ibmi.example.com",
        "UID": "{DJUSER}",
        "PWD": "{s3cr;et}}pw}",
        "SSL": "1",
        "DBQ": "DJTEST",
        "CMT": "1",
        "NAM": "0",
        "TRUEAUTOCOMMIT": "1",
        "DFT": "5",
        "TFT": "2",
        "XDYNAMIC": "0",
        "UNICODESQL": "1",
        "CCSID": "1208",
    }


def test_connection_string_password_is_brace_quoted() -> None:
    assert ";PWD={s3cr;et}}pw};" in connection_string(params())


def test_connection_string_without_tls() -> None:
    assert keywords(connection_string(params(ssl=False)))["SSL"] == "0"


@pytest.mark.parametrize(
    ("level", "cmt"),
    [("*NONE", "0"), ("*CS", "1"), ("*CHG", "2"), ("*ALL", "3"), ("*RR", "4")],
)
def test_connection_string_isolation_level(level: str, cmt: str) -> None:
    assert keywords(connection_string(params(isolation_level=level)))["CMT"] == cmt


def test_connection_string_attributes_override_defaults() -> None:
    dsn = connection_string(params(attributes={"trueautocommit": "0", "BLOCKSIZE": "256"}))
    kw = keywords(dsn)
    assert kw["TRUEAUTOCOMMIT"] == "0"
    assert kw["BLOCKSIZE"] == "256"


def test_connection_string_extended_dynamic_can_be_enabled() -> None:
    attributes = {"XDYNAMIC": "1", "DFTPKGLIB": "DJPKG", "PKG": "A/DEFAULT(IBM),2,0,1,0,512"}
    kw = keywords(connection_string(params(attributes=attributes)))
    assert kw["XDYNAMIC"] == "1"
    assert kw["DFTPKGLIB"] == "DJPKG"
    assert kw["PKG"] == "A/DEFAULT(IBM),2,0,1,0,512"


@pytest.mark.parametrize(
    "keyword", ["PWD", "uid", "DRIVER", "SYSTEM", "DBQ", "SSL", "CMT", "UNICODESQL", "ccsid"]
)
def test_connection_string_rejects_reserved_attributes(keyword: str) -> None:
    with pytest.raises(ValueError, match="cannot be set through attributes"):
        connection_string(params(attributes={keyword: "X"}))


@pytest.mark.parametrize(
    "overrides",
    [
        {"attributes": {"BLOCKSIZE": "1;PWD=x"}},
        {"attributes": {"BLOCK SIZE": "1"}},
        {"default_schema": "LIB;X"},
        {"default_schema": ""},
        {"host": "h{x}"},
    ],
)
def test_connection_string_rejects_injection(overrides: dict) -> None:
    with pytest.raises(ValueError) as info:
        connection_string(params(**overrides))
    assert PASSWORD not in str(info.value)


# --- Isolation levels -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("*CS", "*CS"),
        ("cs", "*CS"),
        ("read committed", "*CS"),
        ("READ_COMMITTED", "*CS"),
        ("*none", "*NONE"),
        ("NC", "*NONE"),
        ("UR", "*CHG"),
        ("repeatable read", "*ALL"),
        ("RS", "*ALL"),
        ("serializable", "*RR"),
    ],
)
def test_normalize_isolation_level(value: str, expected: str) -> None:
    assert base.normalize_isolation_level(value) == expected


def test_normalize_isolation_level_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown isolation level"):
        base.normalize_isolation_level("snapshot")


# --- Error mapping ------------------------------------------------------------

DUPLICATE_KEY = (
    "[23000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0803 - "
    "Duplicate key value specified. (-803) (SQLExecDirectW)"
)
NOT_JOURNALED = (
    "[HY000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL7008 - "
    "DJPROBE in DJTEST not valid for operation. (-7008) (SQLExecDirectW)"
)
TOO_BIG = (
    "[22001] [IBM][System i Access ODBC Driver]Column 2: CWB0111 - "
    "Input data is too big to fit into field (30207) (SQLExecDirectW)"
)
CHECK_VIOLATED = (
    "[HY000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0545 - "
    "INSERT, UPDATE, or MERGE not allowed by CHECK constraint. (-545) (SQLExecDirectW)"
)
# The message texts of SQL0544 and SQL0530-SQL0532 follow IBM's message file; IBM i
# reported them with SQLSTATE HY000 (docs/IBMI_NOTES.md: probe w13 and the
# check_journal notes). Only the SQLCODE decides the class.
CHECK_NOT_ADDED = (
    "[HY000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0544 - "
    "CHECK constraint TESTAPP_BOOK_PAGES cannot be added. (-544) (SQLExecDirectW)"
)
FK_NO_PARENT = (
    "[HY000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0530 - "
    "Operation not allowed by referential constraint TESTAPP_LINK_FK in DJTEST. "
    "(-530) (SQLExecDirectW)"
)
FK_UPDATE_PARENT = (
    "[HY000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0531 - "
    "Update prevented by referential constraint TESTAPP_LINK_FK in DJTEST. "
    "(-531) (SQLExecDirectW)"
)
FK_DELETE_PARENT = (
    "[HY000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0532 - "
    "Delete prevented by referential constraint TESTAPP_LINK_FK in DJTEST. "
    "(-532) (SQLExecDirectW)"
)
SYNTAX = (
    "[42000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0104 - "
    "Token ISOLATION was not valid. (-104) (SQLExecDirectW)"
)


@pytest.mark.parametrize(
    ("exc", "cls", "sqlstate", "sqlcode"),
    [
        (pyodbc.IntegrityError("23000", DUPLICATE_KEY), base.IntegrityError, "23000", -803),
        (pyodbc.Error("HY000", NOT_JOURNALED), base.OperationalError, "HY000", -7008),
        (pyodbc.Error("HY000", CHECK_VIOLATED), base.IntegrityError, "HY000", -545),
        (pyodbc.Error("HY000", CHECK_NOT_ADDED), base.IntegrityError, "HY000", -544),
        (pyodbc.Error("HY000", FK_NO_PARENT), base.IntegrityError, "HY000", -530),
        (pyodbc.Error("HY000", FK_UPDATE_PARENT), base.IntegrityError, "HY000", -531),
        (pyodbc.Error("HY000", FK_DELETE_PARENT), base.IntegrityError, "HY000", -532),
        # The standard foreign key SQLSTATE, should a driver report it.
        (pyodbc.Error("23503", "[23503] fk violation"), base.IntegrityError, "23503", None),
        (pyodbc.DataError("22001", TOO_BIG), base.DataError, "22001", None),
        (pyodbc.ProgrammingError("42000", SYNTAX), base.ProgrammingError, "42000", -104),
        (
            pyodbc.OperationalError("08001", "[08001] link failure"),
            base.OperationalError,
            "08001",
            None,
        ),
        (pyodbc.InterfaceError("IM002", "[IM002] no driver"), base.InterfaceError, "IM002", None),
        (pyodbc.Error("HYT00", "[HYT00] Timeout expired"), base.OperationalError, "HYT00", None),
        (pyodbc.Error("HY000", "[HY000] general error"), base.DatabaseError, "HY000", None),
    ],
)
def test_translate_error_classifies(exc, cls, sqlstate, sqlcode) -> None:
    error = translate_error(exc)
    assert type(error) is cls
    assert error.sqlstate == sqlstate
    assert error.sqlcode == sqlcode


def test_translate_error_falls_back_to_native_class() -> None:
    # pyodbc-internal errors use (message, sqlstate) and a generic SQLSTATE.
    exc = pyodbc.ProgrammingError(
        "The SQL contains 1 parameter markers, but 2 parameters were supplied", "HY000"
    )
    error = translate_error(exc)
    assert type(error) is base.ProgrammingError
    assert error.sqlstate == "HY000"
    assert "1 parameter markers" in str(error)


def test_translate_error_explains_missing_journal() -> None:
    error = translate_error(pyodbc.Error("HY000", NOT_JOURNALED))
    assert "SQL7008" in str(error)
    assert "needs a QSQJRN journal" in str(error)


def test_errors_are_dbapi_hierarchy() -> None:
    for name in ("DataError", "OperationalError", "IntegrityError", "ProgrammingError"):
        assert issubclass(getattr(base, name), base.DatabaseError)
    assert issubclass(base.DatabaseError, base.Error)
    assert issubclass(base.InterfaceError, base.Error)


# --- Redaction ---------------------------------------------------------------

SIGNON_FAILED = (
    "[28000] [IBM][System i Access ODBC Driver]Communication link failure. comm rc=8002 - "
    "CWBSY0002 - Password for user DJUSER on system ibmi.example.com is not correct, "
    "Password length = 10, Prompt Mode = Never, System IP Address = 192.0.2.1"
)


def test_redact_password_and_length() -> None:
    text = base.redact(f"{SIGNON_FAILED} {PASSWORD}", [PASSWORD])
    assert PASSWORD not in text
    assert "Password length = ***" in text
    assert "10," not in text


def test_translate_error_redacts() -> None:
    exc = pyodbc.Error("28000", f"{SIGNON_FAILED} echo={PASSWORD}")
    error = translate_error(exc, [PASSWORD])
    assert type(error) is base.OperationalError
    assert PASSWORD not in str(error)
    assert "Password length = ***" in str(error)


def test_connect_error_carries_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def failing_connect(dsn: str, **kwargs):
        seen["dsn"] = dsn
        raise pyodbc.Error("28000", f"{SIGNON_FAILED} dsn={dsn}")

    monkeypatch.setattr(pyodbc, "connect", failing_connect)
    with pytest.raises(base.OperationalError) as info:
        pyodbc_driver.Driver().connect(params())
    error = info.value
    assert PASSWORD not in str(error)
    assert f"PWD={{{PASSWORD}" not in str(error)
    # The native error (which carried the secret) is not chained.
    assert error.__cause__ is None
    assert error.__context__ is None
    assert seen["dsn"].count("PWD=") == 1


class FakeRawConnection:
    maxwrite = 0  # pyodbc's default: chunk by the driver's type sizes

    def __init__(self):
        self.encoding = None

    def setencoding(self, encoding, ctype):
        self.encoding = (encoding, ctype)


def test_connect_disables_pooling(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    def fake_connect(dsn: str, **kwargs):
        calls.update(kwargs, pooling=pyodbc.pooling)
        return FakeRawConnection()

    monkeypatch.setattr(pyodbc, "pooling", True)
    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    pyodbc_driver.Driver().connect(params(login_timeout=7), autocommit=True)
    assert calls == {"timeout": 7, "autocommit": True, "pooling": False}


def test_connect_sets_maxwrite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pyodbc, "connect", lambda dsn, **kwargs: FakeRawConnection())
    connection = pyodbc_driver.Driver().connect(params())
    assert connection._raw.maxwrite == pyodbc_driver.MAXWRITE


def test_connect_sends_text_as_utf8_through_the_narrow_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pyodbc, "connect", lambda dsn, **kwargs: FakeRawConnection())
    connection = pyodbc_driver.Driver().connect(params())
    assert connection._raw.encoding == ("utf-8", pyodbc.SQL_CHAR)


@pytest.fixture
def fresh_locale_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pyodbc_driver, "_locale_warned", False)
    monkeypatch.setattr(pyodbc, "connect", lambda dsn, **kwargs: FakeRawConnection())

    def codeset(name: str) -> None:
        monkeypatch.setattr(pyodbc_driver.locale, "nl_langinfo", lambda item: name)

    return codeset


def test_non_utf8_locale_warns_once_at_connect(fresh_locale_warning, caplog) -> None:
    fresh_locale_warning("ANSI_X3.4-1968")
    with caplog.at_level("WARNING", logger="django_db2_for_i"):
        pyodbc_driver.Driver().connect(params())
        pyodbc_driver.Driver().connect(params())
    warnings = [r for r in caplog.records if "process locale is not UTF-8" in r.getMessage()]
    assert len(warnings) == 1
    assert "codeset ANSI_X3.4-1968" in warnings[0].getMessage()
    assert "LANG=C.UTF-8" in warnings[0].getMessage()


@pytest.mark.parametrize("codeset", ["UTF-8", "utf8"])
def test_utf8_locale_does_not_warn(fresh_locale_warning, caplog, codeset) -> None:
    fresh_locale_warning(codeset)
    with caplog.at_level("WARNING", logger="django_db2_for_i"):
        pyodbc_driver.Driver().connect(params())
    assert "process locale" not in caplog.text


def test_maxwrite_covers_every_accepted_string() -> None:
    longest = "\U0001f600" * (pyodbc_driver.MAX_STRING_PARAM_UNITS // 2)
    assert len(longest.encode("utf-16-le")) <= pyodbc_driver.MAXWRITE
    assert len(longest.encode("utf-8")) <= pyodbc_driver.MAXWRITE
    assert len(("\u20ac" * pyodbc_driver.MAX_STRING_PARAM_UNITS).encode()) <= pyodbc_driver.MAXWRITE


def test_params_repr_hides_password() -> None:
    assert PASSWORD not in repr(params())


# --- Cursor wrapper --------------------------------------------------------------


def wrap(raw, connection=None):
    """A driver cursor around ``raw`` (on a connection whose raw object is unused)."""
    return pyodbc_driver.Cursor(raw, (), connection or pyodbc_driver.Connection(object(), ()))


class FakeRawCursor:
    def __init__(self, error: Exception | None = None):
        self.calls: list[tuple] = []
        self.error = error

    def execute(self, *args):
        self.calls.append(args)
        if self.error:
            raise self.error


def test_cursor_execute_without_params_sends_sql_only() -> None:
    raw = FakeRawCursor()
    wrap(raw).execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
    assert raw.calls == [("SELECT 1 FROM SYSIBM.SYSDUMMY1",)]


def test_cursor_execute_with_params() -> None:
    raw = FakeRawCursor()
    wrap(raw).execute("VALUES ?", [1])
    assert raw.calls == [("VALUES ?", [1])]


def test_cursor_execute_translates_errors() -> None:
    raw = FakeRawCursor(pyodbc.IntegrityError("23000", DUPLICATE_KEY))
    with pytest.raises(base.IntegrityError) as info:
        wrap(raw).execute("INSERT INTO T VALUES (1)")
    assert info.value.__context__ is None


# --- Statements that leave the connection unusable ---------------------------------

NOT_AUTHORIZED = (
    "[IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0443 - NOT AUTHORIZED TO COMMAND "
    "WRKPTFGRP. (-443) (SQLExecDirectW)"
)
IN_USE = (
    "[IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0519 - Prepared statement STMT0002 "
    "in use. (-519) (SQLPrepare)"
)


def test_sql0443_with_parameters_marks_the_connection_unusable() -> None:
    connection = pyodbc_driver.Connection(object(), ())
    raw = FakeRawCursor(pyodbc.Error("HY000", NOT_AUTHORIZED))
    with pytest.raises(base.Error) as info:
        wrap(raw, connection).execute("SELECT 1 FROM QSYS2.GROUP_PTF_INFO WHERE X LIKE ?", ["%"])
    assert info.value.sqlcode == -443  # the real cause is re-raised as it is
    assert connection.usable is False


def test_sql0443_without_parameters_keeps_the_connection_usable() -> None:
    connection = pyodbc_driver.Connection(object(), ())
    raw = FakeRawCursor(pyodbc.Error("HY000", NOT_AUTHORIZED))
    with pytest.raises(base.Error):
        wrap(raw, connection).execute("SELECT 1 FROM QSYS2.GROUP_PTF_INFO")
    assert connection.usable is True


def test_other_errors_keep_the_connection_usable() -> None:
    connection = pyodbc_driver.Connection(object(), ())
    raw = FakeRawCursor(pyodbc.IntegrityError("23000", DUPLICATE_KEY))
    with pytest.raises(base.IntegrityError):
        wrap(raw, connection).execute("INSERT INTO T VALUES (?)", [1])
    assert connection.usable is True


@pytest.mark.parametrize("parameterized", [False, True])
def test_sql0519_marks_the_connection_unusable_with_a_clear_error(parameterized) -> None:
    connection = pyodbc_driver.Connection(object(), ())
    raw = FakeRawCursor(pyodbc.Error("HY000", IN_USE))
    with pytest.raises(base.OperationalError, match="needs to be closed") as info:
        wrap(raw, connection).execute("VALUES ?", [1]) if parameterized else wrap(
            raw, connection
        ).execute("VALUES 1")
    assert info.value.sqlcode == -519
    # Replaced from None: the sanitized SQL0519 error is not chained as the cause.
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert connection.usable is False


def test_sql0519_during_fetch_marks_the_connection_unusable() -> None:
    connection = pyodbc_driver.Connection(object(), ())

    class FailingFetch:
        def fetchmany(self, size):
            raise pyodbc.Error("HY000", IN_USE)

    with pytest.raises(base.OperationalError):
        wrap(FailingFetch(), connection).fetchmany(100)  # iterator() fetches in chunks
    assert connection.usable is False


class FakeRow(list):
    """Stands in for pyodbc.Row: a sequence that is not a tuple."""


class FakeFetchCursor:
    def fetchone(self):
        return FakeRow([1, "a"])

    def fetchmany(self, size):
        return [FakeRow([i]) for i in range(size)]

    def fetchall(self):
        return [FakeRow([1]), FakeRow([2])]


def test_cursor_fetch_returns_tuples() -> None:
    cursor = wrap(FakeFetchCursor())
    assert type(cursor.fetchone()) is tuple
    assert cursor.fetchone() == (1, "a")
    assert cursor.fetchmany(2) == [(0,), (1,)]
    assert all(type(row) is tuple for row in cursor.fetchall())


def test_cursor_fetchone_end_of_data() -> None:
    raw = FakeFetchCursor()
    raw.fetchone = lambda: None
    assert wrap(raw).fetchone() is None


# --- Secrets never appear in tracebacks ------------------------------------------


def test_secrets_repr_is_redacted() -> None:
    secrets = params().secrets
    assert PASSWORD in secrets  # still usable for redaction
    assert PASSWORD not in repr(secrets)
    assert PASSWORD not in str(secrets)


def frame_values(error: BaseException) -> list[str]:
    """repr() of every argument and local in the error's traceback frames."""
    values = []
    tb = error.__traceback__
    while tb is not None:
        values.extend(repr(value) for value in tb.tb_frame.f_locals.values())
        tb = tb.tb_next
    return values


def test_connect_traceback_frames_carry_no_password(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_connect(dsn: str, **kwargs):
        raise pyodbc.Error("28000", f"{SIGNON_FAILED} dsn={dsn}")

    monkeypatch.setattr(pyodbc, "connect", failing_connect)
    with pytest.raises(base.OperationalError) as info:
        pyodbc_driver.Driver().connect(params())
    values = frame_values(info.value)
    assert values, "expected traceback frames"
    assert not [value for value in values if PASSWORD in value]


def test_cursor_traceback_frames_carry_no_password() -> None:
    raw = FakeRawCursor(pyodbc.IntegrityError("23000", DUPLICATE_KEY))
    with pytest.raises(base.IntegrityError) as info:
        pyodbc_driver.Cursor(raw, params().secrets, pyodbc_driver.Connection(object(), ())).execute(
            "INSERT INTO T VALUES (1)"
        )
    assert not [value for value in frame_values(info.value) if PASSWORD in value]


def test_binary_constructor() -> None:
    # Django's BinaryField.get_db_prep_value() calls connection.Database.Binary().
    assert base.Binary(b"\x00\x01") == b"\x00\x01"
    assert base.Binary(memoryview(b"ab")) == b"ab"


# --- Long string guard (LOB data loss) ---------------------------------------------


class RecordingRawCursor:
    def __init__(self):
        self.calls = []

    def execute(self, *args):
        self.calls.append(("execute", *args))

    def executemany(self, *args):
        self.calls.append(("executemany", *args))


LIMIT = pyodbc_driver.MAX_STRING_PARAM_UNITS


@pytest.mark.parametrize(
    "value",
    ["x" * LIMIT, "é" * LIMIT, "\U0001f600" * (LIMIT // 2), b"\x00" * 100_000, 10**30],
    ids=["ascii at limit", "accented at limit", "emoji at limit", "long bytes", "int"],
)
def test_values_up_to_the_limit_are_sent(value) -> None:
    raw = RecordingRawCursor()
    wrap(raw).execute("VALUES ?", [value])
    assert raw.calls == [("execute", "VALUES ?", [value])]


@pytest.mark.parametrize(
    "value",
    ["x" * (LIMIT + 1), "é" * (LIMIT + 1), "a" + "\U0001f600" * (LIMIT // 2)],
    ids=["ascii", "accented", "emoji counts two units"],
)
def test_longer_strings_are_refused_before_sending(value) -> None:
    raw = RecordingRawCursor()
    with pytest.raises(base.NotSupportedError, match="longer than 1M characters are refused"):
        wrap(raw).execute("VALUES ?, ?", [1, value])
    assert raw.calls == []


def test_executemany_checks_every_row() -> None:
    raw = RecordingRawCursor()
    rows = [["short"], ["x" * (LIMIT + 1)]]
    message = f"String parameter 1 has {LIMIT + 1} UTF-16 units"
    with pytest.raises(base.NotSupportedError, match=message):
        wrap(raw).executemany("VALUES ?", rows)
    assert raw.calls == []


def test_sql_without_params_is_not_checked() -> None:
    raw = RecordingRawCursor()
    wrap(raw).execute("VALUES '" + "x" * (LIMIT + 10) + "'")
    assert len(raw.calls) == 1


def test_guard_reaches_django_as_not_supported_error() -> None:
    import django.db
    from django.db import connection

    with (
        pytest.raises(django.db.NotSupportedError, match="longer than 1M characters are refused"),
        connection.wrap_database_errors,
    ):
        wrap(RecordingRawCursor()).execute("VALUES ?", ["x" * (LIMIT + 1)])


def test_ints_beyond_64_bits_are_bound_as_decimals() -> None:
    """pyodbc refuses a Python int beyond 64 bits (OverflowError); a Decimal binds
    exactly (probe numeric_params)."""
    from decimal import Decimal

    from django_db2_for_i.drivers.pyodbc import bindable_params

    params = (1, 2**63 - 1, 2**63, -(2**63), -(2**63) - 1, True, "x", Decimal("1.5"))
    assert bindable_params(params) == [
        1,
        2**63 - 1,
        Decimal(2**63),
        -(2**63),
        Decimal(-(2**63) - 1),
        True,
        "x",
        Decimal("1.5"),
    ]
    unchanged = (1, "x", None)
    assert bindable_params(unchanged) is unchanged
