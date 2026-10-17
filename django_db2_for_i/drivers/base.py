"""Driver interface: connect, cursor, error mapping, type conversion.

Everything here is driver independent and knows nothing about Django:

- a DB-API 2.0 exception hierarchy shared by all drivers. The backend exposes
  this module as ``DatabaseWrapper.Database``, so Django wraps these classes;
- ``ConnectionParams``: what a driver needs to open a connection;
- commitment control levels and their aliases;
- mapping of Db2 for i SQLSTATE / SQLCODE values to exception classes;
- redaction of secrets from driver messages;
- the abstract ``Driver``, ``Connection`` and ``Cursor`` interfaces.

Drivers translate their native errors into the classes below. The parameter
style of ``Cursor.execute`` is qmark (``?``).
"""

from __future__ import annotations

import abc
import dataclasses
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

# --- DB-API 2.0 exceptions ----------------------------------------------------


class Warning(Exception):  # DB-API 2.0 name, shadows the builtin on purpose
    pass


class Error(Exception):
    """Base class of all driver errors.

    ``sqlstate`` and ``sqlcode`` are those reported by the server or driver
    (``sqlcode`` is ``None`` when unknown). The message never contains secrets.
    """

    def __init__(self, message: str = "", *, sqlstate: str = "", sqlcode: int | None = None):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.sqlcode = sqlcode


class InterfaceError(Error):
    pass


class DatabaseError(Error):
    pass


class DataError(DatabaseError):
    pass


class OperationalError(DatabaseError):
    pass


class IntegrityError(DatabaseError):
    pass


class InternalError(DatabaseError):
    pass


class ProgrammingError(DatabaseError):
    pass


class NotSupportedError(DatabaseError):
    pass


apilevel = "2.0"
paramstyle = "qmark"

# --- Connection parameters ------------------------------------------------------

DEFAULT_LOGIN_TIMEOUT = 10


@dataclasses.dataclass(frozen=True)
class ConnectionParams:
    """Driver-independent connection parameters.

    ``default_schema`` is the library used for unqualified names (``None``:
    the driver's default). ``attributes`` are driver-specific extras (e.g.
    ODBC keywords).
    """

    host: str
    user: str
    password: str = dataclasses.field(repr=False)
    default_schema: str | None
    ssl: bool = True
    isolation_level: str = "*CS"
    login_timeout: int = DEFAULT_LOGIN_TIMEOUT
    attributes: Mapping[str, str] = dataclasses.field(default_factory=dict)

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self.password,) if self.password else ()


# --- Commitment control -----------------------------------------------------------

# IBM i commitment control levels, from no isolation to the strongest.
ISOLATION_LEVELS = ("*NONE", "*CHG", "*CS", "*ALL", "*RR")

_ISOLATION_ALIASES = {
    "NONE": "*NONE",
    "NC": "*NONE",
    "NO COMMIT": "*NONE",
    "CHG": "*CHG",
    "UR": "*CHG",
    "READ UNCOMMITTED": "*CHG",
    "CS": "*CS",
    "READ COMMITTED": "*CS",
    "ALL": "*ALL",
    "RS": "*ALL",
    "REPEATABLE READ": "*ALL",
    "RR": "*RR",
    "SERIALIZABLE": "*RR",
}


def normalize_isolation_level(value: str) -> str:
    """Return the IBM i name (``*CS`` etc.) for a level name or SQL/ANSI alias."""
    key = " ".join(str(value).replace("_", " ").split()).upper()
    if key in ISOLATION_LEVELS:
        return key
    try:
        return _ISOLATION_ALIASES[key.lstrip("*")]
    except KeyError:
        choices = ", ".join(ISOLATION_LEVELS)
        raise ValueError(f"unknown isolation level {value!r}; use one of {choices}") from None


# --- Secrets ------------------------------------------------------------------------

# IBM i sign-on messages (CWBSY0002) include "Password length = <n>".
_PASSWORD_LENGTH = re.compile(r"(password length\s*=\s*)\d+", re.IGNORECASE)


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """Remove secrets and the password length from a message."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return _PASSWORD_LENGTH.sub(r"\1***", text)


# --- Error mapping --------------------------------------------------------------

JOURNAL_REQUIRED_HINT = (
    "The table's library needs a QSQJRN journal: commitment control (transactions, "
    "and every data change with TRUEAUTOCOMMIT=1) requires journaled tables. "
    "Create the library with CREATE SCHEMA, or create a QSQJRN journal in it."
)

# SQLCODEs whose SQLSTATE is too generic (e.g. HY000) to classify them.
_SQLCODE_ERRORS: dict[int, tuple[type[Error], str | None]] = {
    -7008: (OperationalError, JOURNAL_REQUIRED_HINT),  # object not valid for operation
}

# SQLSTATE class (first two characters) -> exception class.
_SQLSTATE_CLASSES: dict[str, type[Error]] = {
    "08": OperationalError,  # connection exception
    "0A": NotSupportedError,  # feature not supported
    "21": DataError,  # cardinality violation
    "22": DataError,  # data exception
    "23": IntegrityError,  # constraint violation
    "24": ProgrammingError,  # invalid cursor state
    "25": OperationalError,  # invalid transaction state
    "28": OperationalError,  # invalid authorization
    "40": OperationalError,  # transaction rollback (deadlock, timeout)
    "42": ProgrammingError,  # syntax error or access rule violation
    "57": OperationalError,  # resource not available / operator intervention
    "58": InternalError,  # system error
    "IM": InterfaceError,  # ODBC driver manager
}

# Full SQLSTATEs that differ from their class.
_SQLSTATE_ERRORS: dict[str, type[Error]] = {
    "HYT00": OperationalError,  # timeout expired
    "HYT01": OperationalError,  # connection timeout expired
}


def error_class(sqlstate: str, sqlcode: int | None) -> type[Error]:
    """Classify a server/driver error. Unknown errors are ``DatabaseError``."""
    if sqlcode in _SQLCODE_ERRORS:
        return _SQLCODE_ERRORS[sqlcode][0]
    sqlstate = sqlstate.upper()
    if sqlstate in _SQLSTATE_ERRORS:
        return _SQLSTATE_ERRORS[sqlstate]
    return _SQLSTATE_CLASSES.get(sqlstate[:2], DatabaseError)


def make_error(
    message: str,
    sqlstate: str = "",
    sqlcode: int | None = None,
    secrets: Sequence[str] = (),
    default: type[Error] | None = None,
) -> Error:
    """Build the exception for a server/driver error, with secrets removed.

    ``default`` is used instead of ``DatabaseError`` when neither SQLSTATE nor
    SQLCODE classifies the error (drivers pass what their native class implies).
    """
    cls = error_class(sqlstate, sqlcode)
    if cls is DatabaseError and default is not None:
        cls = default
    message = redact(message, secrets)
    hint = _SQLCODE_ERRORS.get(sqlcode, (None, None))[1]
    if hint:
        message = f"{message}\n{hint}"
    return cls(message, sqlstate=sqlstate, sqlcode=sqlcode)


# --- Interfaces -------------------------------------------------------------------


class Cursor(abc.ABC):
    """DB-API cursor subset used by the backend. Parameter style: qmark."""

    @property
    @abc.abstractmethod
    def description(self) -> Sequence[tuple] | None: ...

    @property
    @abc.abstractmethod
    def rowcount(self) -> int: ...

    @abc.abstractmethod
    def execute(self, sql: str, params: Sequence[Any] | None = None) -> Cursor:
        """Execute ``sql``. With ``params=None`` the SQL is sent without parameters."""

    @abc.abstractmethod
    def executemany(self, sql: str, param_list: Sequence[Sequence[Any]]) -> Cursor: ...

    @abc.abstractmethod
    def fetchone(self) -> tuple | None: ...

    @abc.abstractmethod
    def fetchmany(self, size: int) -> list[tuple]: ...

    @abc.abstractmethod
    def fetchall(self) -> list[tuple]: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    def __iter__(self) -> Iterator[tuple]:
        return iter(self.fetchone, None)

    def __enter__(self) -> Cursor:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class Connection(abc.ABC):
    @property
    @abc.abstractmethod
    def autocommit(self) -> bool: ...

    @autocommit.setter
    @abc.abstractmethod
    def autocommit(self, value: bool) -> None: ...

    @abc.abstractmethod
    def cursor(self) -> Cursor: ...

    @abc.abstractmethod
    def commit(self) -> None: ...

    @abc.abstractmethod
    def rollback(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def server_version(self) -> str:
        """The server's version string, e.g. ``07.05.0015`` (VV.RR.MMMM)."""


class Driver(abc.ABC):
    name: str

    @abc.abstractmethod
    def connect(self, params: ConnectionParams, autocommit: bool = False) -> Connection:
        """Open one connection. Fails fast and never retries."""
