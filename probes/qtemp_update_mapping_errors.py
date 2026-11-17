"""Does UPDATE or INSERT ... SELECT write NULL for a mapping error? (audit F-04, P-3)

In a select list Db2 for i turns a failed conversion, a division by zero or a
timestamp past 9999-12-31 into NULL without an error (probes ``fetch_errors``
and ``mapping_errors``). The user docs say an ``UPDATE`` then writes that
NULL; no probe backed it. This probe records, for a nullable and a NOT NULL
column each:

- ``UPDATE ... SET col = CAST('abc' AS INTEGER)`` (through a column value);
- ``UPDATE ... SET col = col / 0`` (a zero from a column);
- ``UPDATE ... SET ts = ts + 30 DAYS`` near 9999-12-31, and
  ``ts + 10**15 MICROSECONDS``;
- the same values through ``INSERT ... SELECT``;
- the backend's own form of ``F("ts") + timedelta(days=30)`` (``DAYS`` and
  ``MICROSECONDS`` from a ``BIGINT`` parameter), in an ``UPDATE`` and in a
  select list, and ``TS + 30 DAYS`` in a plain select list, for comparison;
- whether ``RAISE_ERROR('22008', ...)`` inside ``CASE`` is accepted on 7.5 (a
  way for the backend to turn such a NULL into an error).

For each: the statement's outcome, the driver's messages (warnings), the row
count, and the row as it is afterwards.

Writes only to QTEMP (one table, gone with the job), without commitment
control (CMT=0). One connection, one statement per step, no retries.

Usage (inside the "tests" container):
    nox -s probe -- update_mapping_errors

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PUPDM"
COLUMNS = (
    "ID INTEGER NOT NULL, S VARCHAR(10), Z INTEGER, "
    "N INTEGER, NN INTEGER NOT NULL, TS TIMESTAMP, TSNN TIMESTAMP NOT NULL"
)
ROW = "(1, 'abc', 0, 5, 5, '9999-12-30-00.00.00', '9999-12-30-00.00.00')"

UPDATES = (
    ("cast 'abc', nullable", "N = CAST(S AS INTEGER)"),
    ("cast 'abc', NOT NULL", "NN = CAST(S AS INTEGER)"),
    ("divide by zero, nullable", "N = N / Z"),
    ("divide by zero, NOT NULL", "NN = NN / Z"),
    ("timestamp + 30 days, nullable", "TS = TS + 30 DAYS"),
    ("timestamp + 30 days, NOT NULL", "TSNN = TSNN + 30 DAYS"),
    ("timestamp + 10**15 microseconds, nullable", "TS = TS + 1000000000000000 MICROSECONDS"),
    ("timestamp + 10**15 microseconds, NOT NULL", "TSNN = TSNN + 1000000000000000 MICROSECONDS"),
)

INSERTS = (
    (
        "cast 'abc', nullable",
        "SELECT 2, S, Z, CAST(S AS INTEGER), 5, TS, TSNN FROM {t} WHERE ID = 1",
    ),
    (
        "cast 'abc', NOT NULL",
        "SELECT 2, S, Z, 5, CAST(S AS INTEGER), TS, TSNN FROM {t} WHERE ID = 1",
    ),
    ("divide by zero, nullable", "SELECT 2, S, Z, N / Z, 5, TS, TSNN FROM {t} WHERE ID = 1"),
    ("divide by zero, NOT NULL", "SELECT 2, S, Z, 5, NN / Z, TS, TSNN FROM {t} WHERE ID = 1"),
    (
        "timestamp + 30 days, nullable",
        "SELECT 2, S, Z, 5, 5, TS + 30 DAYS, TSNN FROM {t} WHERE ID = 1",
    ),
    (
        "timestamp + 30 days, NOT NULL",
        "SELECT 2, S, Z, 5, 5, TS, TSNN + 30 DAYS FROM {t} WHERE ID = 1",
    ),
)

RAISE = (
    (
        "RAISE_ERROR in CASE, taken",
        "VALUES CASE WHEN 1 = 1 THEN RAISE_ERROR('22008', 'datetime overflow') ELSE 1 END",
    ),
    (
        "RAISE_ERROR in CASE, not taken",
        "VALUES CASE WHEN 1 = 0 THEN RAISE_ERROR('22008', 'datetime overflow') ELSE 1 END",
    ),
    (
        "RAISE_ERROR when the value is NULL",
        "SELECT CASE WHEN TS + 30 DAYS IS NULL THEN "
        "RAISE_ERROR('22008', 'datetime overflow') ELSE TS + 30 DAYS END "
        f"FROM {TABLE} WHERE ID = 1",
    ),
)


def connection_attributes(settings: Settings) -> dict[str, str]:
    """The backend's attributes without commitment control: QTEMP tables have
    no journal, so a write under it is refused (SQL7008)."""
    import pyodbc

    pyodbc.pooling = False
    return {**BACKEND, "CMT": "0"}


# The backend's SQL for a datetime column plus a DurationField value
# (golden expressions/duration_datetime_plus_field, with a parameter).
BACKEND_PLUS = (
    "TS + INTEGER((CAST(? AS BIGINT)) / 86400000000) DAYS "
    "+ MOD((CAST(? AS BIGINT)), 86400000000) MICROSECONDS"
)
THIRTY_DAYS_US = 30 * 86_400_000_000


def _write(conn, sql: str, params=()) -> dict[str, Any]:
    """The outcome of one write with the driver's messages and row count."""
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return {
            "result": "ok",
            "rowcount": cursor.rowcount,
            "messages": [str(message)[:160] for message in cursor.messages] or "none",
        }
    except pyodbc.Error as exc:
        return {"result": "error", "message": str(exc)[:160]}
    finally:
        cursor.close()


def _reset(conn) -> None:
    _execute(conn, f"DELETE FROM {TABLE}")
    _execute(conn, f"INSERT INTO {TABLE} VALUES {ROW}")


def _rows(conn) -> dict[str, Any]:
    return _query(conn, f"SELECT ID, N, NN, TS, TSNN FROM {TABLE} ORDER BY ID")


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table, gone with the job), CMT=0"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(results, "create", _execute(conn, f"CREATE TABLE {TABLE} ({COLUMNS})"))
    if created["result"] != "ok":
        return results
    for label, assignment in UPDATES:
        _reset(conn)
        _step(results, f"UPDATE, {label}", _write(conn, f"UPDATE {TABLE} SET {assignment}"))
        _step(results, f"UPDATE, {label}: rows after", _rows(conn))
    for label, select in INSERTS:
        _reset(conn)
        _step(
            results,
            f"INSERT ... SELECT, {label}",
            _write(conn, f"INSERT INTO {TABLE} {select.format(t=TABLE)}"),
        )
        _step(results, f"INSERT ... SELECT, {label}: rows after", _rows(conn))
    _reset(conn)
    _step(
        results,
        "UPDATE, backend's datetime + duration",
        _write(conn, f"UPDATE {TABLE} SET TS = {BACKEND_PLUS}", (THIRTY_DAYS_US, THIRTY_DAYS_US)),
    )
    _step(results, "UPDATE, backend's datetime + duration: rows after", _rows(conn))
    _step(
        results,
        "SELECT, backend's datetime + duration",
        _query(conn, f"SELECT {BACKEND_PLUS} FROM {TABLE}", (THIRTY_DAYS_US, THIRTY_DAYS_US)),
    )
    _step(results, "SELECT, TS + 30 DAYS", _query(conn, f"SELECT TS + 30 DAYS FROM {TABLE}"))
    for label, sql in RAISE:
        _step(results, label, _query(conn, sql))
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
