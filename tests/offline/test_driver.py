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


@pytest.mark.parametrize("keyword", ["PWD", "uid", "DRIVER", "SYSTEM", "DBQ", "SSL", "CMT"])
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
SYNTAX = (
    "[42000] [IBM][System i Access ODBC Driver][DB2 for i5/OS]SQL0104 - "
    "Token ISOLATION was not valid. (-104) (SQLExecDirectW)"
)


@pytest.mark.parametrize(
    ("exc", "cls", "sqlstate", "sqlcode"),
    [
        (pyodbc.IntegrityError("23000", DUPLICATE_KEY), base.IntegrityError, "23000", -803),
        (pyodbc.Error("HY000", NOT_JOURNALED), base.OperationalError, "HY000", -7008),
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


def test_connect_disables_pooling(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    def fake_connect(dsn: str, **kwargs):
        calls.update(kwargs, pooling=pyodbc.pooling)
        return object()

    monkeypatch.setattr(pyodbc, "pooling", True)
    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    pyodbc_driver.Driver().connect(params(login_timeout=7), autocommit=True)
    assert calls == {"timeout": 7, "autocommit": True, "pooling": False}


def test_params_repr_hides_password() -> None:
    assert PASSWORD not in repr(params())


# --- Cursor wrapper --------------------------------------------------------------


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
    pyodbc_driver.Cursor(raw, ()).execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
    assert raw.calls == [("SELECT 1 FROM SYSIBM.SYSDUMMY1",)]


def test_cursor_execute_with_params() -> None:
    raw = FakeRawCursor()
    pyodbc_driver.Cursor(raw, ()).execute("VALUES ?", [1])
    assert raw.calls == [("VALUES ?", [1])]


def test_cursor_execute_translates_errors() -> None:
    raw = FakeRawCursor(pyodbc.IntegrityError("23000", DUPLICATE_KEY))
    with pytest.raises(base.IntegrityError) as info:
        pyodbc_driver.Cursor(raw, ()).execute("INSERT INTO T VALUES (1)")
    assert info.value.__context__ is None


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
    cursor = pyodbc_driver.Cursor(FakeFetchCursor(), ())
    assert type(cursor.fetchone()) is tuple
    assert cursor.fetchone() == (1, "a")
    assert cursor.fetchmany(2) == [(0,), (1,)]
    assert all(type(row) is tuple for row in cursor.fetchall())


def test_cursor_fetchone_end_of_data() -> None:
    raw = FakeFetchCursor()
    raw.fetchone = lambda: None
    assert pyodbc_driver.Cursor(raw, ()).fetchone() is None


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
        pyodbc_driver.Cursor(raw, params().secrets).execute("INSERT INTO T VALUES (1)")
    assert not [value for value in frame_values(info.value) if PASSWORD in value]
