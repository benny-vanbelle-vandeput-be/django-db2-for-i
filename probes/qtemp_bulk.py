"""The limits of a multi-row INSERT, for ``bulk_batch_size()`` (phase 5, step 0).

Writes only to QTEMP (tables that disappear with the job); reads nothing
outside it. Without commitment control (CMT=0): QTEMP tables have no journal.

- **Parameter markers:** ``INSERT ... VALUES (?, ?), (?, ?), ...`` with 2 and
  with 10 columns, doubling the rows until Db2 for i or the driver refuses,
  then halving the gap to the largest count that works. The SQLCODE of the
  first refusal is recorded.
- **Statement length:** the same with literals instead of markers (long
  string constants), to find the statement length limit apart from the
  marker limit.
- **Rows:** a plain multi-row insert with only constants, to see whether the
  number of rows itself has a limit.

At most about 60 statements; every step stops at the first refusal, so the
probe never retries a failing size.

Usage (inside the "tests" container):
    nox -s probe -- bulk

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PBLK"
START_ROWS = 256
MAX_ROWS = 65536
BISECT_STEPS = 6


def _create(conn, results, columns: int) -> bool:
    _execute(conn, f"DROP TABLE {TABLE}")
    cols = ", ".join(f"C{i} INTEGER" for i in range(columns))
    return _execute(conn, f"CREATE TABLE {TABLE} ({cols})")["result"] == "ok"


def _markers(conn, rows: int, columns: int) -> dict[str, Any]:
    row = "(" + ", ".join(["?"] * columns) + ")"
    sql = f"INSERT INTO {TABLE} VALUES " + ", ".join([row] * rows)
    _execute(conn, f"DELETE FROM {TABLE}")
    return {**_execute(conn, sql, [1] * (rows * columns)), "statement_length": len(sql)}


def _literals(conn, rows: int, width: int) -> dict[str, Any]:
    row = "('" + "x" * width + "')"
    sql = f"INSERT INTO {TABLE} VALUES " + ", ".join([row] * rows)
    _execute(conn, f"DELETE FROM {TABLE}")
    return {**_execute(conn, sql), "statement_length": len(sql)}


def _constants(conn, rows: int) -> dict[str, Any]:
    sql = f"INSERT INTO {TABLE} VALUES " + ", ".join(["(1)"] * rows)
    _execute(conn, f"DELETE FROM {TABLE}")
    return {**_execute(conn, sql), "statement_length": len(sql)}


def _limit(results, key: str, attempt) -> None:
    """Double the size from START_ROWS until a refusal, then bisect."""
    good, bad, first_error = 0, None, None
    size = START_ROWS
    while size <= MAX_ROWS:
        outcome = attempt(size)
        print(f"    {key}: {size} -> {outcome['result']}")
        if outcome["result"] != "ok":
            bad, first_error = size, outcome
            break
        good = size
        size *= 2
    steps = 0
    while bad is not None and bad - good > 1 and steps < BISECT_STEPS:
        middle = (good + bad) // 2
        outcome = attempt(middle)
        print(f"    {key}: {middle} -> {outcome['result']}")
        if outcome["result"] == "ok":
            good = middle
        else:
            bad, first_error = middle, outcome
        steps += 1
    _step(
        results,
        key,
        {"largest_ok": good, "smallest_refused": bad, "refusal": first_error},
    )


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    for columns in (2, 10):
        if _create(conn, results, columns):
            _limit(
                results,
                f"rows with parameter markers, {columns} columns",
                lambda rows, c=columns: _markers(conn, rows, c),
            )
    _execute(conn, f"DROP TABLE {TABLE}")
    if _execute(conn, f"CREATE TABLE {TABLE} (C VARCHAR(1000))")["result"] == "ok":
        _limit(
            results, "rows of a 1000-character literal", lambda rows: _literals(conn, rows, 1000)
        )
    _execute(conn, f"DROP TABLE {TABLE}")
    if _execute(conn, f"CREATE TABLE {TABLE} (C INTEGER)")["result"] == "ok":
        _limit(results, "rows of the constant 1", lambda rows: _constants(conn, rows))
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
