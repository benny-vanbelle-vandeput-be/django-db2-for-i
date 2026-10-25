"""ADD COLUMN ... NOT NULL without a default, and the spellings of a bare DEFAULT (SQL0109).

Writes only to QTEMP (one table at a time, gone with the job), with the
backend's connection attributes. Django's AddField of a NOT NULL field without
any default writes ``ADD COLUMN c <type> NOT NULL``, which Db2 for i rejects
with SQL0109 ("NOT NULL clause not allowed"; IBM's SQL reference: NOT NULL
needs DEFAULT unless the column is an identity column).

For each base column type the backend writes (DatabaseWrapper.data_types),
on an empty table and on a table with one row:

- the statement without a default (expected: SQL0109);
- each spelling of a bare DEFAULT, the type's system default: ``DEFAULT NOT
  NULL``, ``NOT NULL DEFAULT``, ``NOT NULL WITH DEFAULT``, ``WITH DEFAULT NOT
  NULL``; then ``ALTER COLUMN c DROP DEFAULT``, and on the table with a row the
  value the existing row got.

Then ``LOCK TABLE ... IN EXCLUSIVE MODE`` and ``IN SHARE MODE`` on a QTEMP
table, in a transaction and in autocommit: whether Db2 for i accepts them (what
the lock allows *other* jobs needs a table outside QTEMP: lib_lock_table,
#162). UNIQUE with NOT NULL cannot be tried here (a constraint on a QTEMP table
fails with SQL7008); the goldens cover it.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute, _rows

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PANN"
TYPES = [
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "DECIMAL(9, 2)",
    "DOUBLE",
    "BOOLEAN",
    "CHAR(32)",
    "VARCHAR(39)",
    "NVARCHAR(40)",
    "NCLOB",
    "BLOB",
    "DATE",
    "TIME",
    "TIMESTAMP(6)",
]
SPELLINGS = {
    "no default": "{type} NOT NULL",
    "DEFAULT NOT NULL": "{type} DEFAULT NOT NULL",
    "NOT NULL DEFAULT": "{type} NOT NULL DEFAULT",
    "NOT NULL WITH DEFAULT": "{type} NOT NULL WITH DEFAULT",
    "WITH DEFAULT NOT NULL": "{type} WITH DEFAULT NOT NULL",
}


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _outcome(result: dict[str, Any]) -> str:
    if result["result"] == "ok":
        return "ok"
    return f"SQL{abs(result.get('sqlcode') or 0):04d} ({result.get('sqlstate')})"


def _value(conn) -> str:
    try:
        rows = _rows(conn, f"SELECT C FROM {TABLE}")
    except Exception as exc:  # LOBs and the like: record, do not fail the probe
        return f"unreadable: {exc}"
    return repr(rows[0][0]) if rows else "no row"


def _case(conn, column_type: str, spelling: str, *, with_row: bool) -> dict[str, Any]:
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER)")
    if created["result"] != "ok":
        raise RuntimeError(f"setup failed: {created}")
    if with_row:
        _execute(conn, f"INSERT INTO {TABLE} (ID) VALUES (1)")
    definition = SPELLINGS[spelling].format(type=column_type)
    added = _execute(conn, f"ALTER TABLE {TABLE} ADD COLUMN C {definition}")
    result: dict[str, Any] = {"add": _outcome(added)}
    if added["result"] != "ok":
        result["message"] = added.get("message", "")
        return result
    if with_row:
        result["existing row"] = _value(conn)
    dropped = _execute(conn, f"ALTER TABLE {TABLE} ALTER COLUMN C DROP DEFAULT")
    result["drop default"] = _outcome(dropped)
    insert = _execute(conn, f"INSERT INTO {TABLE} (ID) VALUES (2)")
    result["insert without C afterwards"] = _outcome(insert)
    return result


def _locks(conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    _execute(conn, f"DROP TABLE {TABLE}")
    _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER)")
    for mode in ("EXCLUSIVE", "SHARE"):
        for label, autocommit in (("autocommit", True), ("transaction", False)):
            conn.autocommit = autocommit
            try:
                outcome = _execute(conn, f"LOCK TABLE {TABLE} IN {mode} MODE")
                results[f"{mode} MODE, {label}"] = _outcome(outcome)
            finally:
                if not autocommit:
                    conn.rollback()
                conn.autocommit = True
    return results


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"table": TABLE, "connection": BACKEND, "types": {}}
    try:
        for column_type in TYPES:
            per_type: dict[str, Any] = {}
            for spelling in SPELLINGS:
                for with_row in (False, True):
                    key = f"{spelling}, {'one row' if with_row else 'empty'}"
                    per_type[key] = _case(conn, column_type, spelling, with_row=with_row)
            results["types"][column_type] = per_type
            summary = "  ".join(
                f"{key}:{value['add']}" for key, value in per_type.items() if "empty" in key
            )
            print(f"  {column_type:<14} {summary}")
        results["locks"] = _locks(conn)
        print(f"  locks: {results['locks']}")
    finally:
        conn.autocommit = True
        _execute(conn, f"DROP TABLE {TABLE}")
    return results
