"""What Db2 for i supports for the feature flags once marked "later" (#191, topic 3).

Writes only to QTEMP (tables that disappear with the job); reads nothing
outside it. Each statement's outcome is recorded with its SQLSTATE and
SQLCODE. Db2 for i syntax, not PostgreSQL's (the maintainer's decision on
#191): a materialized view is a materialized query table, and generated
columns are tried in several forms.

- ``has_real_datatype``: a ``REAL`` column and the value it returns.
- ``supports_no_precision_decimalfield``: ``DECIMAL`` without precision, and
  ``DECFLOAT(34)`` / ``DECFLOAT(16)`` round trips of ``Decimal`` values.
- ``supports_unlimited_charfield``: ``NVARCHAR`` / ``VARCHAR`` without a length.
- ``supports_collation_on_*``, ``supports_non_deterministic_collations``: a
  ``COLLATE`` clause on a column.
- ``supports_stored_generated_columns``, ``supports_virtual_generated_columns``,
  ``supports_alter_generated_column_data_type``: ``GENERATED ALWAYS AS``
  forms (an expression on other columns, with STORED / VIRTUAL, special
  registers, row change timestamp, identity as the control), the value they
  produce, and a data type change of the generated column.
- ``can_introspect_materialized_views``: ``CREATE MATERIALIZED VIEW`` (Django's
  test) and an MQT (``CREATE TABLE ... AS (...) DATA INITIALLY DEFERRED
  REFRESH DEFERRED MAINTAINED BY USER``), refreshed and read, and what the
  driver's catalog function (``SQLTables``) reports for it.
- ``truncates_names``: a 129-character table name.

Usage (inside the "tests" container):
    nox -s probe -- later_flags

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute

NEEDS_CONNECTION = True
AUTOCOMMIT = True

PREFIX = "QTEMP.PLF"


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _query(conn, sql: str, params=()) -> dict[str, Any]:
    """The rows of a query with the driver's description of each column."""
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return {
            "result": "ok",
            "columns": [
                {
                    "name": name,
                    "type": getattr(type_code, "__name__", str(type_code)),
                    "size": size,
                    "precision": precision,
                    "scale": scale,
                }
                for name, type_code, _display, size, precision, scale, _null in cursor.description
            ],
            "rows": [[repr(value) for value in row] for row in rows],
        }
    except pyodbc.Error as exc:
        return {"result": "error", **_execute_error(exc)}
    finally:
        cursor.close()


def _execute_error(exc) -> dict[str, Any]:
    from qtemp_alter_table import _PREFIX, _SQLCODE

    message = str(exc.args[1] if len(exc.args) > 1 else exc)
    match = _SQLCODE.search(message)
    return {
        "sqlstate": str(exc.args[0]) if exc.args else "",
        "sqlcode": int(match.group(1)) if match else None,
        "message": _PREFIX.sub("", message)[:120],
    }


def _step(results: dict[str, Any], key: str, outcome: dict[str, Any]) -> dict[str, Any]:
    results[key] = outcome
    print(f"  {key}: {outcome}")
    return outcome


def _table(conn, results, key: str, name: str, columns: str) -> bool:
    _execute(conn, f"DROP TABLE {PREFIX}{name}")
    return (
        _step(results, key, _execute(conn, f"CREATE TABLE {PREFIX}{name} ({columns})"))["result"]
        == "ok"
    )


def _real(conn, results) -> None:
    if _table(conn, results, "real: create", "R", "R REAL"):
        _step(
            results, "real: insert 1.5", _execute(conn, f"INSERT INTO {PREFIX}R VALUES (?)", [1.5])
        )
        _step(results, "real: read", _query(conn, f"SELECT R FROM {PREFIX}R"))
        _execute(conn, f"DROP TABLE {PREFIX}R")


def _decimals(conn, results) -> None:
    if _table(conn, results, "decimal without precision: create", "D", "D DECIMAL"):
        _step(
            results, "decimal without precision: describe", _query(conn, f"SELECT D FROM {PREFIX}D")
        )
        for value in ("12345", "123456", "1.5"):
            _step(
                results,
                f"decimal without precision: insert {value}",
                _execute(conn, f"INSERT INTO {PREFIX}D VALUES (?)", [Decimal(value)]),
            )
        _step(results, "decimal without precision: read", _query(conn, f"SELECT D FROM {PREFIX}D"))
        _execute(conn, f"DROP TABLE {PREFIX}D")
    values = (
        "12345678901234567890.123456789",
        "0.1",
        "-1E-30",
        "123456789012345678901234567890.1234",
        "1E+300",
    )
    for digits in (34, 16):
        name = f"F{digits}"
        if not _table(conn, results, f"decfloat({digits}): create", name, f"F DECFLOAT({digits})"):
            continue
        for value in values:
            _execute(conn, f"DELETE FROM {PREFIX}{name}")
            _step(
                results,
                f"decfloat({digits}): insert {value}",
                _execute(conn, f"INSERT INTO {PREFIX}{name} VALUES (?)", [Decimal(value)]),
            )
            read = _query(conn, f"SELECT F FROM {PREFIX}{name}")
            _step(
                results, f"decfloat({digits}): read {value}", {**read, "sent": repr(Decimal(value))}
            )
        _execute(conn, f"DROP TABLE {PREFIX}{name}")


def _lengths(conn, results) -> None:
    for type_ in ("NVARCHAR", "VARCHAR", "VARGRAPHIC"):
        _table(conn, results, f"{type_} without a length: create", "L", f"C {type_}")
    _execute(conn, f"DROP TABLE {PREFIX}L")


def _collations(conn, results) -> None:
    for i, clause in enumerate(
        (
            "COLLATE UNICODE",
            'COLLATE "UCA500R1_LEN_S1"',
            "COLLATE UCA500R1_LEN_S1",
            "COLLATE SYSTEM",
            "CCSID 1200 COLLATE UNICODE",
        )
    ):
        _table(conn, results, f"column with {clause}: create", f"C{i}", f"C NVARCHAR(10) {clause}")
        _execute(conn, f"DROP TABLE {PREFIX}C{i}")


GENERATED_FORMS = {
    "expression": "B INTEGER GENERATED ALWAYS AS (A * 2)",
    "expression, STORED": "B INTEGER GENERATED ALWAYS AS (A * 2) STORED",
    "expression, VIRTUAL": "B INTEGER GENERATED ALWAYS AS (A * 2) VIRTUAL",
    "AS (expression), no GENERATED": "B INTEGER AS (A * 2)",
    "expression, cast": "B BIGINT GENERATED ALWAYS AS (CAST(A AS BIGINT) + 1)",
    "special register (USER)": "B VARCHAR(18) GENERATED ALWAYS AS (USER)",
    "special register (CURRENT TIMESTAMP)": "B TIMESTAMP GENERATED ALWAYS AS (CURRENT TIMESTAMP)",
    "data change operation": "B CHAR(1) GENERATED ALWAYS AS (DATA CHANGE OPERATION)",
    "row change timestamp": (
        "B TIMESTAMP NOT NULL GENERATED ALWAYS FOR EACH ROW ON UPDATE AS ROW CHANGE TIMESTAMP"
    ),
    "identity (control)": "B INTEGER GENERATED ALWAYS AS IDENTITY",
}


def _generated(conn, results) -> None:
    for i, (label, column) in enumerate(GENERATED_FORMS.items()):
        name = f"G{i}"
        key = f"generated column, {label}"
        if not _table(conn, results, f"{key}: create", name, f"A INTEGER, {column}"):
            continue
        _step(
            results,
            f"{key}: insert A=3",
            _execute(conn, f"INSERT INTO {PREFIX}{name} (A) VALUES (3)"),
        )
        _step(results, f"{key}: update A=4", _execute(conn, f"UPDATE {PREFIX}{name} SET A = 4"))
        _step(results, f"{key}: read", _query(conn, f"SELECT A, B FROM {PREFIX}{name}"))
        if label.startswith("expression"):
            _step(
                results,
                f"{key}: ALTER COLUMN B SET DATA TYPE BIGINT",
                _execute(conn, f"ALTER TABLE {PREFIX}{name} ALTER COLUMN B SET DATA TYPE BIGINT"),
            )
            _step(
                results,
                f"{key}: read after the type change",
                _query(conn, f"SELECT A, B FROM {PREFIX}{name}"),
            )
        _execute(conn, f"DROP TABLE {PREFIX}{name}")


def _materialized(conn, results) -> None:
    if not _table(conn, results, "mqt: base table", "BASE", "ID INTEGER, NAME NVARCHAR(10)"):
        return
    _execute(conn, f"INSERT INTO {PREFIX}BASE VALUES (1, 'a'), (2, 'b')")
    _step(
        results,
        "CREATE MATERIALIZED VIEW (Django's test)",
        _execute(conn, f"CREATE MATERIALIZED VIEW {PREFIX}MV AS SELECT ID, NAME FROM {PREFIX}BASE"),
    )
    _execute(conn, f"DROP TABLE {PREFIX}MQT")
    created = _step(
        results,
        "mqt: create (DATA INITIALLY DEFERRED REFRESH DEFERRED MAINTAINED BY USER)",
        _execute(
            conn,
            f"CREATE TABLE {PREFIX}MQT AS (SELECT ID, NAME FROM {PREFIX}BASE) "
            "DATA INITIALLY DEFERRED REFRESH DEFERRED MAINTAINED BY USER",
        ),
    )
    if created["result"] == "ok":
        _step(
            results, "mqt: read before refresh", _query(conn, f"SELECT COUNT(*) FROM {PREFIX}MQT")
        )
        _step(results, "mqt: refresh", _execute(conn, f"REFRESH TABLE {PREFIX}MQT"))
        _step(results, "mqt: read after refresh", _query(conn, f"SELECT COUNT(*) FROM {PREFIX}MQT"))
        _step(results, "mqt: driver catalog (SQLTables)", _tables(conn, "PLFMQT"))
        _step(results, "base table: driver catalog (SQLTables)", _tables(conn, "PLFBASE"))
        _execute(conn, f"DROP TABLE {PREFIX}MQT")
    _execute(conn, f"DROP TABLE {PREFIX}BASE")


def _tables(conn, table: str) -> dict[str, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        rows = cursor.tables(table=table, schema="QTEMP").fetchall()
        return {
            "result": "ok",
            "rows": [{"table": row.table_name, "type": row.table_type} for row in rows],
        }
    except pyodbc.Error as exc:
        return {"result": "error", **_execute_error(exc)}
    finally:
        cursor.close()


def _long_name(conn, results) -> None:
    name = "T" * 129
    _step(
        results,
        "table name of 129 characters",
        _execute(conn, f"CREATE TABLE QTEMP.{name} (A INTEGER)"),
    )
    _execute(conn, f"DROP TABLE QTEMP.{name}")
    name = "T" * 128
    _step(
        results,
        "table name of 128 characters",
        _execute(conn, f"CREATE TABLE QTEMP.{name} (A INTEGER)"),
    )
    _execute(conn, f"DROP TABLE QTEMP.{name}")


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    for part in (_real, _decimals, _lengths, _collations, _generated, _materialized, _long_name):
        print(f" -- {part.__name__.strip('_')}")
        part(conn, results)
    return results
