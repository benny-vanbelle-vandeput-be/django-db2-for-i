"""How large can a BinaryField value be? (audit F-14, remediation P-5)

``BinaryField`` is ``BLOB`` without a length in this backend. Db2 for i's
default length for ``BLOB`` is 1 MiB; the user docs say bytes are not limited.
This probe records:

- an ``INSERT`` of 512 KiB, 1 MiB and 2 MiB into a ``BLOB`` column (a plain
  marker, as a model save writes it), and the stored length;
- the same with 5 MiB into a ``BLOB(10M)`` column (the driver's chunked path
  for long values).

Writes only to QTEMP (one table, gone with the job), without commitment
control (CMT=0). One connection, one statement per step, no retries. About
8.5 MiB is sent in total.

Usage (inside the "tests" container):
    nox -s probe -- blob_default_length

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PBLOB"
KIB = 1024
CASES = (
    ("B", "512 KiB into BLOB", 512 * KIB),
    ("B", "1 MiB into BLOB", 1024 * KIB),
    ("B", "2 MiB into BLOB", 2048 * KIB),
    ("B10", "5 MiB into BLOB(10M)", 5120 * KIB),
)


def connection_attributes(settings: Settings) -> dict[str, str]:
    """The backend's attributes without commitment control (QTEMP has no journal)."""
    import pyodbc

    pyodbc.pooling = False
    return {**BACKEND, "CMT": "0"}


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table), CMT=0"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(
        results,
        "create",
        _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER NOT NULL, B BLOB, B10 BLOB(10M))"),
    )
    if created["result"] != "ok":
        return results
    for number, (column, label, size) in enumerate(CASES, 1):
        _step(
            results,
            label,
            _execute(
                conn,
                f"INSERT INTO {TABLE} (ID, {column}) VALUES (?, ?)",
                (number, bytes(range(256)) * (size // 256)),
            ),
        )
        _step(
            results,
            f"{label}: stored length",
            _query(conn, f"SELECT LENGTH({column}) FROM {TABLE} WHERE ID = ?", (number,)),
        )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
