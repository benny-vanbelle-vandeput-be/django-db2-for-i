"""What does an INSERT of a Decimal with more decimals than its column do? (F-06, P-5)

``qtemp_decimal_values`` showed that a cast marker refuses a value with more
decimals (22001). A model ``save()`` writes a plain marker into a
``DECIMAL(5, 2)`` column. This probe records an ``INSERT`` into such a column
of ``Decimal("1.005")``, ``Decimal("1.2345")``, ``Decimal("1.004")`` and
``Decimal("1.23")``:

- through a plain marker (``VALUES (?)``), as a model save writes it;
- through a typed marker (``CAST(? AS DECIMAL(5, 2))``);
- the value stored afterwards, if any (rounded, truncated, or refused).

Writes only to QTEMP (one table, gone with the job), without commitment
control (CMT=0). One connection, one statement per step, no retries.

Usage (inside the "tests" container):
    nox -s probe -- decimal_assignment

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PDECA"
VALUES = ("1.005", "1.2345", "1.004", "1.23")
MARKERS = (("plain marker", "?"), ("typed marker", "CAST(? AS DECIMAL(5, 2))"))


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
        _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER NOT NULL, D DECIMAL(5, 2))"),
    )
    if created["result"] != "ok":
        return results
    number = 0
    for label, marker in MARKERS:
        for value in VALUES:
            number += 1
            _step(
                results,
                f"{label}, {value}",
                _execute(
                    conn, f"INSERT INTO {TABLE} VALUES (?, {marker})", (number, Decimal(value))
                ),
            )
            _step(
                results,
                f"{label}, {value}: stored",
                _query(conn, f"SELECT D FROM {TABLE} WHERE ID = ?", (number,)),
            )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
