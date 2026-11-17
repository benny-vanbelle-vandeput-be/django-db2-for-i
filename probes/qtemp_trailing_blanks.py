"""Do 'abc' and 'abc ' compare equal? (audit F-05, remediation P-4)

Db2 pads the shorter string with blanks before comparing, for ``CHAR`` and, per
the documentation, also for ``VARCHAR`` and ``NVARCHAR``. ``CharField`` is
``NVARCHAR`` in this backend. This probe records, for ``NVARCHAR``, ``VARCHAR``
and ``CHAR`` columns that hold ``'abc'`` and ``'abc '``:

- ``=`` with a literal and with a parameter marker, ``IN``;
- ``GROUP BY`` and ``DISTINCT`` (how many groups);
- ``LIKE`` with the backend's form (``LIKE ? ESCAPE '\\'``), ``'abc'`` and
  ``'abc '``;
- ``LENGTH`` of each stored value;
- a unique index created over the two rows (``ALTER TABLE ... ADD
  CONSTRAINT ... UNIQUE`` is refused in QTEMP with SQL7008).

Writes only to QTEMP (one table per type, gone with the job), without
commitment control (CMT=0). One connection, one statement per step, no
retries.

Usage (inside the "tests" container):
    nox -s probe -- trailing_blanks

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TYPES = (("NVARCHAR", "NVARCHAR(10)"), ("VARCHAR", "VARCHAR(10)"), ("CHAR", "CHAR(10)"))


def connection_attributes(settings: Settings) -> dict[str, str]:
    """The backend's attributes without commitment control (QTEMP has no journal)."""
    import pyodbc

    pyodbc.pooling = False
    return {**BACKEND, "CMT": "0"}


def _checks(table: str) -> tuple[tuple[str, str, tuple], ...]:
    return (
        ("count = 'abc' (literal)", f"SELECT COUNT(*) FROM {table} WHERE S = 'abc'", ()),
        ("count = ? ('abc')", f"SELECT COUNT(*) FROM {table} WHERE S = ?", ("abc",)),
        ("count = ? ('abc ')", f"SELECT COUNT(*) FROM {table} WHERE S = ?", ("abc ",)),
        ("count IN ('abc')", f"SELECT COUNT(*) FROM {table} WHERE S IN ('abc')", ()),
        (
            "groups (GROUP BY)",
            f"SELECT COUNT(*) FROM (SELECT S FROM {table} GROUP BY S) T",
            (),
        ),
        ("groups (DISTINCT)", f"SELECT COUNT(DISTINCT S) FROM {table}", ()),
        (
            "count LIKE ? ESCAPE ('abc')",
            f"SELECT COUNT(*) FROM {table} WHERE S LIKE ? ESCAPE '\\'",
            ("abc",),
        ),
        (
            "count LIKE ? ESCAPE ('abc ')",
            f"SELECT COUNT(*) FROM {table} WHERE S LIKE ? ESCAPE '\\'",
            ("abc ",),
        ),
        ("lengths", f"SELECT ID, LENGTH(S) FROM {table} ORDER BY ID", ()),
    )


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table per type), CMT=0"}
    for name, column in TYPES:
        table = f"QTEMP.PTB{name[:2]}"
        _execute(conn, f"DROP TABLE {table}")
        created = _step(
            results,
            f"{name}: create",
            _execute(conn, f"CREATE TABLE {table} (ID INTEGER NOT NULL, S {column})"),
        )
        if created["result"] != "ok":
            continue
        _execute(conn, f"INSERT INTO {table} VALUES (1, 'abc'), (2, 'abc ')")
        for label, sql, params in _checks(table):
            _step(results, f"{name}: {label}", _query(conn, sql, params))
        _step(
            results,
            f"{name}: UNIQUE index over 'abc' and 'abc '",
            _execute(conn, f"CREATE UNIQUE INDEX QTEMP.{table[6:]}U ON {table} (S)"),
        )
        _execute(conn, f"DROP TABLE {table}")
    return results
