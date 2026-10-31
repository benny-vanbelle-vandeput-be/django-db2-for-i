"""Does the limit of a multi-row INSERT depend on the column types? (phase 5, step A2)

``qtemp_bulk`` measured INTEGER columns only: 32,767 markers at most. Django's
``lookup.tests.LookupTests.test_in_bulk_lots_of_ids`` then failed with PWS0001
at prepare on 1997 rows of (NVARCHAR(100), NVARCHAR(50), NCLOB), about 6000
markers, inside FINAL TABLE. This finds what the limit depends on: LOB columns,
the declared LOB length, wide character columns, the FINAL TABLE wrapper.

Writes only to QTEMP (tables that disappear with the job); reads nothing
outside it. Without commitment control (CMT=0): QTEMP tables have no journal.

Each case doubles the rows from START_ROWS until a refusal, then bisects, so
at most about 12 statements per case. After a refusal the probe checks that
the connection still answers, and stops at once if it does not.

Usage (inside the "tests" container):
    nox -s probe -- bulk_types

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PBLKT"
START_ROWS = 64
MAX_ROWS = 16384
BISECT_STEPS = 5

AUTHOR = ("NVARCHAR(100)", "NVARCHAR(50)", "NCLOB")

# name, column types, one row's values, inside FINAL TABLE
CASES: tuple[tuple[str, tuple[str, ...], tuple[Any, ...], bool], ...] = (
    ("as the failing test, FINAL TABLE", AUTHOR, ("", None, None), True),
    ("as the failing test, plain INSERT", AUTHOR, ("", None, None), False),
    ("no NCLOB, FINAL TABLE", AUTHOR[:2], ("", None), True),
    ("one NCLOB, plain INSERT", ("NCLOB",), (None,), False),
    ("one NCLOB, non-NULL values", ("NCLOB",), ("x",), False),
    ("one NCLOB(1K)", ("NCLOB(1K)",), (None,), False),
    ("one NCLOB(1M)", ("NCLOB(1M)",), (None,), False),
    ("one NCLOB(100M)", ("NCLOB(100M)",), (None,), False),
    ("one CLOB(1M)", ("CLOB(1M)",), (None,), False),
    ("one BLOB(1M)", ("BLOB(1M)",), (None,), False),
    ("two NCLOB(1M)", ("NCLOB(1M)", "NCLOB(1M)"), (None, None), False),
    ("one NVARCHAR(16000)", ("NVARCHAR(16000)",), (None,), False),
    ("one NVARCHAR(255)", ("NVARCHAR(255)",), (None,), False),
)


def _insert(conn, rows: int, values: tuple[Any, ...], final_table: bool) -> dict[str, Any]:
    row = "(" + ", ".join(["?"] * len(values)) + ")"
    sql = f"INSERT INTO {TABLE} VALUES " + ", ".join([row] * rows)
    if final_table:
        sql = f"SELECT C0 FROM FINAL TABLE ({sql}) ORDER BY INPUT SEQUENCE"
    _execute(conn, f"DELETE FROM {TABLE}")
    return {**_execute(conn, sql, list(values) * rows), "markers": rows * len(values)}


def _alive(conn) -> bool:
    return _execute(conn, "SELECT 1 FROM SYSIBM.SYSDUMMY1")["result"] == "ok"


def _limit(conn, results, key: str, values: tuple[Any, ...], final_table: bool) -> bool:
    """Double from START_ROWS until a refusal, then bisect. False: connection lost."""
    good, bad, first_error = 0, None, None
    size = START_ROWS
    while size <= MAX_ROWS:
        outcome = _insert(conn, size, values, final_table)
        print(f"    {key}: {size} -> {outcome['result']}")
        if outcome["result"] != "ok":
            bad, first_error = size, outcome
            break
        good = size
        size *= 2
    steps = 0
    usable = bad is None or _alive(conn)
    while usable and bad is not None and bad - good > 1 and steps < BISECT_STEPS:
        middle = (good + bad) // 2
        outcome = _insert(conn, middle, values, final_table)
        print(f"    {key}: {middle} -> {outcome['result']}")
        if outcome["result"] == "ok":
            good = middle
        else:
            bad, first_error = middle, outcome
            usable = _alive(conn)
        steps += 1
    _step(
        results,
        key,
        {
            "largest_ok": good,
            "smallest_refused": bad,
            "refusal": first_error,
            "connection_usable_after": usable,
        },
    )
    return usable


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    for key, types, values, final_table in CASES:
        _execute(conn, f"DROP TABLE {TABLE}")
        columns = ", ".join(f"C{i} {type_}" for i, type_ in enumerate(types))
        if _execute(conn, f"CREATE TABLE {TABLE} ({columns})")["result"] != "ok":
            _step(results, key, {"result": "CREATE TABLE refused"})
            continue
        if not _limit(conn, results, key, values, final_table):
            results["stopped"] = f"the connection no longer answered after: {key}"
            return results
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
