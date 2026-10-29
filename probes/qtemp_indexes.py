"""Partial, expression and covering indexes (phase 5, step 0).

Writes only to QTEMP (tables and indexes that disappear with the job); reads
nothing outside it. Without commitment control (CMT=0): QTEMP tables have no
journal. QTEMP objects do not appear in the catalog (``QSYS2.SYSINDEXES``,
``SYSKEYS``; probe ``qtemp_catalog``), so how the catalog shows these indexes
needs tables in a real library: a separate ``lib_`` probe, only with approval.

- ``supports_partial_indexes``: ``CREATE INDEX ... WHERE <condition>``, also
  ``UNIQUE ... WHERE``, and whether the unique index then allows duplicates
  outside the condition.
- ``supports_functions_in_partial_indexes``: a function in the ``WHERE``.
- ``supports_expression_indexes``: indexes on expressions (``UPPER(B)``,
  ``A + C``, descending, mixed with a plain column), unique ones included.
- ``supports_covering_indexes``: ``INCLUDE (...)``.
- The forms Django writes: quoted names, ``WHERE`` with an inlined constant,
  an ``IS NOT NULL`` condition.

Usage (inside the "tests" container):
    nox -s probe -- indexes

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PIDX"
CREATE = f"CREATE TABLE {TABLE} (A INTEGER, B NVARCHAR(20), C INTEGER)"

INDEXES = {
    "partial: WHERE C > 0": "CREATE INDEX QTEMP.PIDX1 ON QTEMP.PIDX (A) WHERE C > 0",
    "partial: WHERE B IS NOT NULL": (
        "CREATE INDEX QTEMP.PIDX2 ON QTEMP.PIDX (A) WHERE B IS NOT NULL"
    ),
    "partial, quoted names (Django's form)": (
        'CREATE INDEX "QTEMP"."PIDX3" ON "QTEMP"."PIDX" ("A") WHERE "C" > 0'
    ),
    "partial: function, WHERE UPPER(B) = 'X'": (
        "CREATE INDEX QTEMP.PIDX4 ON QTEMP.PIDX (A) WHERE UPPER(B) = 'X'"
    ),
    "partial: function, WHERE LENGTH(B) > 3": (
        "CREATE INDEX QTEMP.PIDX5 ON QTEMP.PIDX (A) WHERE LENGTH(B) > 3"
    ),
    "partial: WHERE with OR and IN": (
        "CREATE INDEX QTEMP.PIDX6 ON QTEMP.PIDX (A) WHERE C IN (1, 2) OR B = 'y'"
    ),
    "expression: UPPER(B)": "CREATE INDEX QTEMP.PIDX7 ON QTEMP.PIDX (UPPER(B))",
    "expression: A + C": "CREATE INDEX QTEMP.PIDX8 ON QTEMP.PIDX (A + C)",
    "expression: LOWER(B) DESC": "CREATE INDEX QTEMP.PIDX9 ON QTEMP.PIDX (LOWER(B) DESC)",
    "expression mixed with a column: (A, UPPER(B))": (
        "CREATE INDEX QTEMP.PIDX10 ON QTEMP.PIDX (A, UPPER(B))"
    ),
    "expression in parentheses (Django's form): ((UPPER(B)))": (
        "CREATE INDEX QTEMP.PIDX11 ON QTEMP.PIDX ((UPPER(B)))"
    ),
    "expression: CAST(A AS VARCHAR(10))": (
        "CREATE INDEX QTEMP.PIDX12 ON QTEMP.PIDX (CAST(A AS VARCHAR(10)))"
    ),
    "expression with a partial condition": (
        "CREATE INDEX QTEMP.PIDX13 ON QTEMP.PIDX (UPPER(B)) WHERE C > 0"
    ),
    "covering: INCLUDE (B)": "CREATE INDEX QTEMP.PIDX14 ON QTEMP.PIDX (A) INCLUDE (B)",
    "covering, unique: UNIQUE ... INCLUDE (B)": (
        "CREATE UNIQUE INDEX QTEMP.PIDX15 ON QTEMP.PIDX (C) INCLUDE (B)"
    ),
}


def _plain(conn, results) -> None:
    for label, sql in INDEXES.items():
        _step(results, label, _execute(conn, sql))


def _unique_partial(conn, results) -> None:
    _execute(conn, f"DELETE FROM {TABLE}")
    created = _step(
        results,
        "unique partial: UNIQUE ... (A) WHERE C > 0",
        _execute(conn, "CREATE UNIQUE INDEX QTEMP.PIDXU1 ON QTEMP.PIDX (A) WHERE C > 0"),
    )
    if created["result"] == "ok":
        _step(
            results,
            "unique partial: two rows A=1 outside the condition (C = 0)",
            _execute(conn, f"INSERT INTO {TABLE} (A, C) VALUES (1, 0), (1, 0)"),
        )
        _step(
            results,
            "unique partial: a row A=1 inside the condition (C = 5)",
            _execute(conn, f"INSERT INTO {TABLE} (A, C) VALUES (1, 5)"),
        )
        _step(
            results,
            "unique partial: a second row A=1 inside the condition (duplicate)",
            _execute(conn, f"INSERT INTO {TABLE} (A, C) VALUES (1, 6)"),
        )
        _execute(conn, "DROP INDEX QTEMP.PIDXU1")
    _execute(conn, f"DELETE FROM {TABLE}")
    created = _step(
        results,
        "unique expression: UNIQUE ... (UPPER(B))",
        _execute(conn, "CREATE UNIQUE INDEX QTEMP.PIDXU2 ON QTEMP.PIDX (UPPER(B))"),
    )
    if created["result"] == "ok":
        _step(
            results,
            "unique expression: 'abc' then 'ABC' (duplicate under UPPER)",
            _execute(conn, f"INSERT INTO {TABLE} (B) VALUES ('abc'), ('ABC')"),
        )
        _execute(conn, "DROP INDEX QTEMP.PIDXU2")


def _used(conn, results) -> None:
    """The partial index does not change query results (the optimizer may use it)."""
    _execute(conn, f"DELETE FROM {TABLE}")
    _execute(conn, f"INSERT INTO {TABLE} (A, B, C) VALUES (1, 'x', 1), (2, 'y', 0), (3, NULL, 2)")
    _step(
        results,
        "query with the partial condition",
        _query(conn, f"SELECT A FROM {TABLE} WHERE C > 0 ORDER BY A"),
    )


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables and indexes gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    if _step(results, "create", _execute(conn, CREATE))["result"] != "ok":
        return results
    for part in (_plain, _unique_partial, _used):
        print(f" -- {part.__name__.strip('_')}")
        part(conn, results)
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
