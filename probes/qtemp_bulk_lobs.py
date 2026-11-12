"""Where the LOB limit of a multi-row statement lies for 3 and 5 LOB columns,
and for MERGE (phase 7, section 3).

``qtemp_bulk_types`` measured 1 and 2 LOB columns: about 1,024 LOB markers,
so ``bulk_batch_size()`` allows ``BULK_MAX_LOB_PARAMS`` (512) LOB markers per
statement. With 3 and 5 columns own IBM i tests show only that the batches
work and that 1,080 or 1,100 markers are refused, not where the limit lies.
This bisects it for 1, 2, 3 and 5 ``NCLOB`` columns next to an ``INTEGER``
key, as a plain ``INSERT``, inside ``FINAL TABLE`` (what ``bulk_create()``
sends), and as the ``MERGE`` of ``ignore_conflicts``; plus one case with
non-NULL values. The result says whether larger batches are possible.

Writes only to QTEMP (tables that disappear with the job); reads nothing
outside it. Without commitment control (CMT=0): QTEMP tables have no journal.

Each case doubles the rows from START_ROWS until a refusal, then bisects, so
at most about 12 statements per case. After a refusal the probe checks that
the connection still answers, and stops at once if it does not.

Usage (inside the "tests" container):
    nox -s probe -- bulk_lobs

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PBLKL"
START_ROWS = 64
MAX_ROWS = 4096
BISECT_STEPS = 6

# name, LOB columns, statement form ("insert", "final", "merge"), LOB value
CASES: tuple[tuple[str, int, str, Any], ...] = (
    ("1 NCLOB, INSERT", 1, "insert", None),
    ("2 NCLOB, INSERT", 2, "insert", None),
    ("3 NCLOB, INSERT", 3, "insert", None),
    ("5 NCLOB, INSERT", 5, "insert", None),
    ("3 NCLOB, FINAL TABLE", 3, "final", None),
    ("5 NCLOB, FINAL TABLE", 5, "final", None),
    ("1 NCLOB, MERGE", 1, "merge", None),
    ("3 NCLOB, MERGE", 3, "merge", None),
    ("5 NCLOB, MERGE", 5, "merge", None),
    ("3 NCLOB, INSERT, non-NULL values", 3, "insert", "x"),
)


def _statement(rows: int, lobs: int, form: str) -> str:
    columns = ["K"] + [f"L{i}" for i in range(lobs)]
    row = "(" + ", ".join(["?"] * len(columns)) + ")"
    values = ", ".join([row] * rows)
    names = ", ".join(columns)
    if form == "merge":
        source = ", ".join(f"S.{name}" for name in columns)
        return (
            f"MERGE INTO {TABLE} AS T USING (VALUES {values}) AS S ({names})"
            f" ON T.K = S.K WHEN NOT MATCHED THEN INSERT ({names}) VALUES ({source})"
        )
    insert = f"INSERT INTO {TABLE} ({names}) VALUES {values}"
    if form == "final":
        return f"SELECT K FROM FINAL TABLE ({insert}) ORDER BY INPUT SEQUENCE"
    return insert


def _run(conn, rows: int, lobs: int, form: str, value: Any) -> dict[str, Any]:
    params: list[Any] = []
    for key in range(rows):
        params += [key] + [value] * lobs
    _execute(conn, f"DELETE FROM {TABLE}")
    outcome = _execute(conn, _statement(rows, lobs, form), params)
    return {**outcome, "markers": rows * (lobs + 1), "lob_markers": rows * lobs}


def _alive(conn) -> bool:
    return _execute(conn, "SELECT 1 FROM SYSIBM.SYSDUMMY1")["result"] == "ok"


def _limit(conn, results, key: str, lobs: int, form: str, value: Any) -> bool:
    """Double from START_ROWS until a refusal, then bisect. False: connection lost."""
    good, bad, first_error = 0, None, None
    size = START_ROWS
    while size <= MAX_ROWS:
        outcome = _run(conn, size, lobs, form, value)
        print(f"    {key}: {size} rows -> {outcome['result']}")
        if outcome["result"] != "ok":
            bad, first_error = size, outcome
            break
        good = size
        size *= 2
    steps = 0
    usable = bad is None or _alive(conn)
    while usable and bad is not None and bad - good > 1 and steps < BISECT_STEPS:
        middle = (good + bad) // 2
        outcome = _run(conn, middle, lobs, form, value)
        print(f"    {key}: {middle} rows -> {outcome['result']}")
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
            "largest_ok_rows": good,
            "largest_ok_lob_markers": good * lobs,
            "smallest_refused_rows": bad,
            "smallest_refused_lob_markers": bad * lobs if bad else None,
            "refusal": first_error,
            "connection_usable_after": usable,
        },
    )
    return usable


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    for key, lobs, form, value in CASES:
        _execute(conn, f"DROP TABLE {TABLE}")
        columns = ", ".join(["K INTEGER"] + [f"L{i} NCLOB(1M)" for i in range(lobs)])
        if _execute(conn, f"CREATE TABLE {TABLE} ({columns})")["result"] != "ok":
            _step(results, key, {"result": "CREATE TABLE refused"})
            continue
        if not _limit(conn, results, key, lobs, form, value):
            results["stopped"] = f"the connection no longer answered after: {key}"
            return results
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
