"""Two cursors at once, and statements with a subquery on their own target
table (phase 5, step 0).

Writes only to QTEMP (tables that disappear with the job); reads nothing
outside it. Without commitment control (CMT=0): QTEMP tables have no journal.

- ``can_use_chunked_reads``: one cursor fetches a result in chunks
  (``fetchmany``) while a second cursor on the same connection reads, inserts
  and updates; are all rows of the first result returned, unchanged?
- ``delete_can_self_reference_subquery``: ``DELETE ... WHERE ID IN (SELECT
  ... FROM <same table>)``, the form Django writes.
- ``update_can_self_select``: ``UPDATE ... SET X = (SELECT ... FROM <same
  table>)`` and ``UPDATE ... WHERE ID IN (SELECT ... FROM <same table>)``.

Usage (inside the "tests" container):
    nox -s probe -- cursors

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _execute_error, _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PCUR"
OTHER = "QTEMP.PCUR2"
ROWS = 300
CHUNK = 100


def _fill(conn) -> bool:
    for name in (TABLE, OTHER):
        _execute(conn, f"DROP TABLE {name}")
    if _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER, X INTEGER)")["result"] != "ok":
        return False
    _execute(conn, f"CREATE TABLE {OTHER} (ID INTEGER)")
    values = ", ".join(f"({i}, {i % 7})" for i in range(1, ROWS + 1))
    return _execute(conn, f"INSERT INTO {TABLE} VALUES {values}")["result"] == "ok"


def _chunked(conn, results, label: str, other_statement: str | None) -> None:
    """Fetch TABLE in chunks; between chunks run other_statement on a second cursor."""
    import pyodbc

    first = conn.cursor()
    second = conn.cursor()
    outcome: dict[str, Any] = {"result": "ok", "between_chunks": []}
    try:
        first.execute(f"SELECT ID, X FROM {TABLE} ORDER BY ID")
        fetched: list[int] = []
        while True:
            chunk = first.fetchmany(CHUNK)
            if not chunk:
                break
            fetched.extend(row[0] for row in chunk)
            if other_statement is not None:
                try:
                    second.execute(other_statement)
                    if second.description:
                        second.fetchall()
                    outcome["between_chunks"].append("ok")
                except pyodbc.Error as exc:
                    outcome["between_chunks"].append({"result": "error", **_execute_error(exc)})
        outcome.update(
            rows=len(fetched),
            all_rows_in_order=fetched == list(range(1, ROWS + 1)),
        )
    except pyodbc.Error as exc:
        outcome = {"result": "error", **_execute_error(exc), **outcome}
    finally:
        first.close()
        second.close()
    _step(results, label, outcome)


def _cursors(conn, results) -> None:
    if not _fill(conn):
        _step(results, "chunked: create", {"result": "error"})
        return
    _chunked(conn, results, "chunked reads, nothing in between (control)", None)
    _chunked(
        conn,
        results,
        "chunked reads, a SELECT on another table in between",
        f"SELECT COUNT(*) FROM {OTHER}",
    )
    _chunked(
        conn,
        results,
        "chunked reads, an INSERT into another table in between",
        f"INSERT INTO {OTHER} VALUES (1)",
    )
    _chunked(
        conn,
        results,
        "chunked reads, an UPDATE of the same table in between",
        f"UPDATE {TABLE} SET X = X + 100 WHERE ID = 250",
    )
    _chunked(
        conn,
        results,
        "chunked reads, a SELECT of the same table in between",
        f"SELECT COUNT(*) FROM {TABLE}",
    )


def _self_reference(conn, results) -> None:
    if not _fill(conn):
        return
    _step(
        results,
        "DELETE ... WHERE ID IN (SELECT ... FROM the same table)",
        _execute(
            conn,
            f'DELETE FROM {TABLE} WHERE "ID" IN (SELECT U0."ID" FROM {TABLE} U0 WHERE U0."X" = 0)',
        ),
    )
    _step(
        results,
        "DELETE ... WHERE ID IN (SELECT ... FROM the same table ... FETCH FIRST)",
        _execute(
            conn,
            f"DELETE FROM {TABLE} WHERE ID IN (SELECT U0.ID FROM {TABLE} U0 ORDER BY U0.ID "
            "FETCH FIRST 5 ROWS ONLY)",
        ),
    )
    _step(
        results,
        "UPDATE ... SET X = (SELECT MAX(X) FROM the same table)",
        _execute(conn, f"UPDATE {TABLE} SET X = (SELECT MAX(U0.X) FROM {TABLE} U0)"),
    )
    _step(
        results,
        "UPDATE ... WHERE ID IN (SELECT ... FROM the same table)",
        _execute(
            conn,
            f"UPDATE {TABLE} SET X = 1 WHERE ID IN (SELECT U0.ID FROM {TABLE} U0 WHERE U0.ID < 50)",
        ),
    )
    _step(
        results,
        "UPDATE ... SET X = (correlated SELECT FROM the same table)",
        _execute(
            conn,
            f"UPDATE {TABLE} T SET X = (SELECT COUNT(*) FROM {TABLE} U0 WHERE U0.ID < T.ID)",
        ),
    )
    _step(results, "after the statements", _query(conn, f"SELECT COUNT(*), MAX(X) FROM {TABLE}"))


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    for part in (_cursors, _self_reference):
        print(f" -- {part.__name__.strip('_')}")
        part(conn, results)
    for name in (TABLE, OTHER):
        _execute(conn, f"DROP TABLE {name}")
    return results
