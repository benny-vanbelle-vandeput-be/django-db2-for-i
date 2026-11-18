"""Which error does a MERGE give for a duplicate key in its own source? (F-16, P-5)

``bulk_create(update_conflicts=True)`` / ``ignore_conflicts`` are written as
one ``MERGE``. When two objects in one batch have the same key, the source
holds two rows for one target key. This probe records the SQLSTATE and
SQLCODE (which decide the Django exception class) for a ``MERGE`` with two
source rows of the same key:

- when the target already has that key (two matches);
- when it does not (two inserts);
- with ``WHEN NOT MATCHED THEN INSERT`` only (as ``ignore_conflicts``).

Writes only to QTEMP (one table, gone with the job), without commitment
control (CMT=0). One connection, one statement per step, no retries.

Usage (inside the "tests" container):
    nox -s probe -- merge_duplicates

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PMRGD"
SOURCE = "(VALUES (1, 'a'), (1, 'b')) S (ID, V)"
UPSERT = (
    f"MERGE INTO {TABLE} T USING {SOURCE} ON T.ID = S.ID "
    "WHEN MATCHED THEN UPDATE SET V = S.V "
    "WHEN NOT MATCHED THEN INSERT (ID, V) VALUES (S.ID, S.V)"
)
INSERT_ONLY = (
    f"MERGE INTO {TABLE} T USING {SOURCE} ON T.ID = S.ID "
    "WHEN NOT MATCHED THEN INSERT (ID, V) VALUES (S.ID, S.V)"
)


def connection_attributes(settings: Settings) -> dict[str, str]:
    """The backend's attributes without commitment control (QTEMP has no journal)."""
    import pyodbc

    pyodbc.pooling = False
    return {**BACKEND, "CMT": "0"}


def _case(conn, results, label: str, *, existing: bool, sql: str) -> None:
    _execute(conn, f"DELETE FROM {TABLE}")
    if existing:
        _execute(conn, f"INSERT INTO {TABLE} VALUES (1, 'x')")
    _step(results, label, _execute(conn, sql))
    _step(results, f"{label}: rows after", _query(conn, f"SELECT ID, V FROM {TABLE}"))


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table), CMT=0"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(
        results,
        "create",
        _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER NOT NULL, V VARCHAR(5))"),
    )
    if created["result"] != "ok":
        return results
    # A key constraint is refused in QTEMP (SQL7008); a unique index works.
    _step(results, "unique index", _execute(conn, f"CREATE UNIQUE INDEX {TABLE}U ON {TABLE} (ID)"))
    _case(conn, results, "upsert, key in the target", existing=True, sql=UPSERT)
    _case(conn, results, "upsert, key not in the target", existing=False, sql=UPSERT)
    _case(conn, results, "insert only, key not in the target", existing=False, sql=INSERT_ONLY)
    _case(conn, results, "insert only, key in the target", existing=True, sql=INSERT_ONLY)
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
