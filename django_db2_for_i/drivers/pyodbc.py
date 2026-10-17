"""pyodbc + IBM i Access ODBC Driver implementation of the driver interface.

Connection defaults (all documented in docs/IBMI_NOTES.md / DECISIONS.md):

- ``NAM=0``: SQL naming (``schema.table``), not system naming.
- ``DBQ=<default schema>``: becomes ``CURRENT SCHEMA``.
- ``CMT``: commitment control level from ``ConnectionParams.isolation_level``
  (default ``*CS``).
- ``TRUEAUTOCOMMIT=1``: autocommit statements run under commitment control,
  so a failing statement leaves no partial changes. Requires journaled tables.
- ``DFT=5`` / ``TFT=2``: ISO date and time formats for string renderings
  (pyodbc itself returns ``datetime`` objects).
- ``XDYNAMIC=0``: no extended dynamic SQL packages. The driver default (1)
  creates ``*SQLPKG`` objects on the server (in ``QGPL`` by default). Django's
  many distinct statements and the test suite's create/drop churn make them
  useless or harmful. To enable them for tuning, pass driver attributes, e.g.
  ``{"XDYNAMIC": "1", "DFTPKGLIB": "<library>", "PKG": "A/DEFAULT(IBM),2,0,1,0,512"}``
  (``DFTPKGLIB``: package library, default ``QGPL``; ``PKG``: package usage,
  see IBM's "Connection string keywords", package properties).
- ``SSL``: TLS on the database host server (port 9471) unless disabled.
- CCSID: pyodbc uses the ODBC wide-character API (UTF-16), so no client CCSID
  keyword is needed; data is converted from the column CCSID by the driver.

``maxwrite``: long string parameters are bound in one buffer instead of in
chunks (see "Long string parameters" below).

pyodbc connection pooling is switched off: Django manages connection reuse,
and shared systems such as PUB400 limit connections per client.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from . import base

DRIVER_NAME = "IBM i Access ODBC Driver"

CONNECTION_DEFAULTS: Mapping[str, str] = {
    "NAM": "0",
    "TRUEAUTOCOMMIT": "1",
    "DFT": "5",
    "TFT": "2",
    "XDYNAMIC": "0",
}

# CMT keyword values per commitment control level, from IBM's "Connection
# string keywords" documentation. Only CMT=1 -> *CS has been verified by a
# probe (session).
COMMIT_MODES: Mapping[str, str] = {
    "*NONE": "0",
    "*CS": "1",
    "*CHG": "2",
    "*ALL": "3",
    "*RR": "4",
}

# Set by the connection itself; attributes cannot override them.
RESERVED_KEYWORDS = frozenset({"DRIVER", "DSN", "SYSTEM", "UID", "PWD", "DBQ", "SSL", "CMT"})

_SQLSTATE = re.compile(r"^[0-9A-Z]{5}$")
# pyodbc formats driver messages as "[SQLSTATE] text (native error) (function)".
# For server errors the native error is the (negative) SQLCODE; errors raised by
# the ODBC driver itself carry positive CWB codes, which are not SQLCODEs.
_SQLCODE = re.compile(r"\((-\d+)\)\s*(?:\(\w+\))?\s*$")


def _braced(value: str) -> str:
    """Brace-quote an ODBC value (handles ';', '=', spaces and '}')."""
    return "{" + value.replace("}", "}}") + "}"


def _plain(name: str, value: str) -> str:
    if not value or any(char in value for char in ";{}="):
        raise ValueError(f"invalid value for connection keyword {name}")
    return value


def connection_string(params: base.ConnectionParams) -> str:
    """Build the ODBC connection string. Never log or print the result."""
    isolation = base.normalize_isolation_level(params.isolation_level)
    keywords: dict[str, str] = {
        "DRIVER": _braced(DRIVER_NAME),
        "SYSTEM": _plain("SYSTEM", params.host),
        "UID": _braced(params.user),
        "PWD": _braced(params.password),
        "SSL": "1" if params.ssl else "0",
        "CMT": COMMIT_MODES[isolation],
        **CONNECTION_DEFAULTS,
    }
    if params.default_schema is not None:
        keywords["DBQ"] = _plain("DBQ", params.default_schema)
    for name, value in params.attributes.items():
        key = str(name).upper()
        if key in RESERVED_KEYWORDS or not key.isalnum():
            raise ValueError(f"connection keyword {name} cannot be set through attributes")
        keywords[key] = _plain(key, str(value))
    return ";".join(f"{key}={value}" for key, value in keywords.items())


# --- Errors ---------------------------------------------------------------------


def _native_class(exc: Exception) -> type[base.Error] | None:
    """The base class matching pyodbc's own classification (same DB-API names)."""
    for cls in type(exc).__mro__:
        mapped = getattr(base, cls.__name__, None)
        if isinstance(mapped, type) and issubclass(mapped, base.Error) and mapped is not base.Error:
            return mapped
    return None


def translate_error(exc: Exception, secrets: Sequence[str] = ()) -> base.Error:
    """Turn a pyodbc error into a driver-independent error without secrets."""
    args = [str(arg) for arg in getattr(exc, "args", ())]
    sqlstate, message = "", str(exc)
    if len(args) >= 2:
        # Driver errors are (sqlstate, message); some pyodbc-internal ones are
        # (message, sqlstate).
        if _SQLSTATE.match(args[0]):
            sqlstate, message = args[0], args[1]
        elif _SQLSTATE.match(args[1]):
            sqlstate, message = args[1], args[0]
        else:
            message = " ".join(args)
    elif args:
        message = args[0]
    match = _SQLCODE.search(message)
    sqlcode = int(match.group(1)) if match else None
    return base.make_error(message, sqlstate, sqlcode, secrets, default=_native_class(exc))


def _call[T](secrets: Sequence[str], func: Callable[..., T], *args: Any) -> T:
    """Call a pyodbc function; raise its errors as driver-independent errors.

    The translated error is raised after the except block, so the native error
    (which may carry secrets) is neither its cause nor its context.
    """
    import pyodbc

    try:
        return func(*args)
    except pyodbc.Error as exc:
        error = translate_error(exc, secrets)
    raise error


# --- Long string parameters -----------------------------------------------------

# pyodbc sends a parameter larger than its limit as data-at-execution, in
# chunks of that limit. Without maxwrite the limit for strings is the driver's
# SQL_WVARCHAR column size, 16369 (characters, compared with bytes): an odd
# chunk size that splits UTF-16 units, which the driver drops for LOB targets
# (probe_encoding, docs/IBMI_NOTES.md). With maxwrite above every accepted
# string, strings are always bound in one buffer.
#
# Maximum: 1M UTF-16 units, the capacity of a TextField column (NCLOB, which
# is NCLOB(1M)). Longer strings are refused before anything is sent, because
# they would be chunked again. Bytes are never refused: above MAXWRITE they
# are chunked too, which is safe for binary data.
MAX_STRING_PARAM_UNITS = 1024 * 1024
# Bytes; covers every accepted string in UTF-16 (2 bytes per unit) and UTF-8
# (at most 3 bytes per UTF-16 unit).
MAXWRITE = 4 * MAX_STRING_PARAM_UNITS


def check_string_params(params: Sequence[Any]) -> None:
    for position, value in enumerate(params, start=1):
        if isinstance(value, str) and len(value) > MAX_STRING_PARAM_UNITS // 2:
            units = len(value.encode("utf-16-le")) // 2
            if units > MAX_STRING_PARAM_UNITS:
                raise base.NotSupportedError(
                    f"String parameter {position} has {units} UTF-16 units; strings longer "
                    f"than {MAX_STRING_PARAM_UNITS} are refused (docs/user/"
                    "Known-Limitations.md, 'Strings longer than 1M characters are refused')."
                )


# --- Connection and cursor ------------------------------------------------------


class Cursor(base.Cursor):
    def __init__(self, raw: Any, secrets: Sequence[str]):
        self._raw = raw
        self._secrets = secrets

    @property
    def description(self) -> Sequence[tuple] | None:
        return self._raw.description

    @property
    def rowcount(self) -> int:
        return self._raw.rowcount

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Cursor:
        if params is None:
            _call(self._secrets, self._raw.execute, sql)
        else:
            check_string_params(params)
            _call(self._secrets, self._raw.execute, sql, params)
        return self

    def executemany(self, sql: str, param_list: Sequence[Sequence[Any]]) -> Cursor:
        for params in param_list:
            check_string_params(params)
        _call(self._secrets, self._raw.executemany, sql, param_list)
        return self

    # pyodbc returns pyodbc.Row objects; the interface promises plain tuples.
    def fetchone(self) -> tuple | None:
        row = _call(self._secrets, self._raw.fetchone)
        return None if row is None else tuple(row)

    def fetchmany(self, size: int) -> list[tuple]:
        return [tuple(row) for row in _call(self._secrets, self._raw.fetchmany, size)]

    def fetchall(self) -> list[tuple]:
        return [tuple(row) for row in _call(self._secrets, self._raw.fetchall)]

    def close(self) -> None:
        _call(self._secrets, self._raw.close)


class Connection(base.Connection):
    def __init__(self, raw: Any, secrets: Sequence[str]):
        self._raw = raw
        self._secrets = secrets

    @property
    def autocommit(self) -> bool:
        return self._raw.autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        _call(self._secrets, setattr, self._raw, "autocommit", value)

    def cursor(self) -> Cursor:
        return Cursor(_call(self._secrets, self._raw.cursor), self._secrets)

    def commit(self) -> None:
        _call(self._secrets, self._raw.commit)

    def rollback(self) -> None:
        _call(self._secrets, self._raw.rollback)

    def close(self) -> None:
        _call(self._secrets, self._raw.close)

    def server_version(self) -> str:
        import pyodbc

        return str(_call(self._secrets, self._raw.getinfo, pyodbc.SQL_DBMS_VER))


class Driver(base.Driver):
    name = "pyodbc"

    def connect(self, params: base.ConnectionParams, autocommit: bool = False) -> Connection:
        import pyodbc

        pyodbc.pooling = False
        # The connection string (with PWD) is built inside _connect(), so it is
        # never a local of a frame that ends up in a traceback.
        raw = _call(params.secrets, _connect, params, autocommit)
        return Connection(raw, params.secrets)


def _connect(params: base.ConnectionParams, autocommit: bool) -> Any:
    import pyodbc

    raw = pyodbc.connect(
        connection_string(params), timeout=params.login_timeout, autocommit=autocommit
    )
    raw.maxwrite = MAXWRITE
    return raw
