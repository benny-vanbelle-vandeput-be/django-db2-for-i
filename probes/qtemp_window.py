"""Window functions as Django writes them, for phase 6 (``supports_over_clause``,
``supports_default_in_lead_lag``, ``supports_frame_range_fixed_distance``,
``supports_frame_exclusion``).

Writes only to QTEMP (a table that disappears with the job); reads nothing
outside it. Without commitment control (CMT=0): QTEMP tables have no journal.
One connection, one statement per case, each outcome recorded with its SQLSTATE
and SQLCODE, no retries. IBM's OLAP page documents ROWS and RANGE but not
EXCLUDE or GROUPS, and does not say whether parameter markers are allowed:
those cases decide what Django's expressions can send.

Usage (inside the "tests" container):
    nox -s probe -- window

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.P6WIN"
ROWS = (
    (1, 1, 10.0, "2026-01-01", "a"),
    (2, 1, 20.0, "2026-01-02", "b"),
    (3, 1, 20.0, "2026-01-08", "c"),
    (4, 2, 40.0, "2026-02-01", "d"),
    (5, 2, None, "2026-02-02", "e"),
)
ORDER = "ORDER BY I"

CASES: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    ("ROW_NUMBER", f"ROW_NUMBER() OVER ({ORDER})", ()),
    ("ROW_NUMBER without ORDER BY", "ROW_NUMBER() OVER ()", ()),
    ("RANK", "RANK() OVER (ORDER BY V)", ()),
    ("DENSE_RANK", "DENSE_RANK() OVER (ORDER BY V)", ()),
    ("PERCENT_RANK", f"PERCENT_RANK() OVER ({ORDER})", ()),
    ("CUME_DIST", f"CUME_DIST() OVER ({ORDER})", ()),
    ("NTILE constant", f"NTILE(2) OVER ({ORDER})", ()),
    ("NTILE marker", f"NTILE(?) OVER ({ORDER})", (2,)),
    ("NTILE typed marker", f"NTILE(CAST(? AS INTEGER)) OVER ({ORDER})", (2,)),
    ("LAG", f"LAG(V) OVER ({ORDER})", ()),
    ("LAG constants", f"LAG(V, 1, 0) OVER ({ORDER})", ()),
    ("LAG offset marker", f"LAG(V, ?) OVER ({ORDER})", (1,)),
    ("LAG typed offset marker", f"LAG(V, CAST(? AS INTEGER)) OVER ({ORDER})", (1,)),
    ("LAG default marker", f"LAG(V, 1, ?) OVER ({ORDER})", (0.0,)),
    ("LAG typed default marker", f"LAG(V, 1, CAST(? AS DOUBLE)) OVER ({ORDER})", (0.0,)),
    (
        "LAG both typed markers",
        f"LAG(V, CAST(? AS INTEGER), CAST(? AS DOUBLE)) OVER ({ORDER})",
        (1, 0.0),
    ),
    ("LEAD", f"LEAD(V, 1) OVER ({ORDER})", ()),
    ("FIRST_VALUE", f"FIRST_VALUE(V) OVER ({ORDER})", ()),
    ("LAST_VALUE", f"LAST_VALUE(V) OVER ({ORDER})", ()),
    ("NTH_VALUE constant", f"NTH_VALUE(V, 2) OVER ({ORDER})", ()),
    ("NTH_VALUE marker", f"NTH_VALUE(V, ?) OVER ({ORDER})", (2,)),
    ("NTH_VALUE typed marker", f"NTH_VALUE(V, CAST(? AS INTEGER)) OVER ({ORDER})", (2,)),
    ("SUM empty window", "SUM(V) OVER ()", ()),
    ("SUM partition", "SUM(V) OVER (PARTITION BY G)", ()),
    ("SUM partition and order", "SUM(V) OVER (PARTITION BY G ORDER BY I)", ()),
    ("AVG cast as the backend does", "AVG(CAST(V AS DOUBLE)) OVER (PARTITION BY G)", ()),
    ("COUNT star", "COUNT(*) OVER (PARTITION BY G)", ()),
    ("PARTITION BY expression", "SUM(V) OVER (PARTITION BY MOD(I, 2))", ()),
    ("PARTITION BY marker expression", "SUM(V) OVER (PARTITION BY MOD(I, ?))", (2,)),
    (
        "ROWS unbounded to current",
        f"SUM(V) OVER ({ORDER} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)",
        (),
    ),
    ("ROWS 1 to 1", f"SUM(V) OVER ({ORDER} ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING)", ()),
    (
        "ROWS current to unbounded",
        f"SUM(V) OVER ({ORDER} ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)",
        (),
    ),
    (
        "RANGE unbounded to current",
        "SUM(V) OVER (ORDER BY V RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)",
        (),
    ),
    (
        "RANGE fixed distance",
        "SUM(V) OVER (ORDER BY V RANGE BETWEEN 5 PRECEDING AND 5 FOLLOWING)",
        (),
    ),
    (
        "RANGE fixed distance, integer key",
        "SUM(V) OVER (ORDER BY I RANGE BETWEEN 1 PRECEDING AND 1 FOLLOWING)",
        (),
    ),
    (
        "RANGE fixed distance, date key",
        "SUM(V) OVER (ORDER BY D RANGE BETWEEN 7 DAYS PRECEDING AND CURRENT ROW)",
        (),
    ),
    (
        "RANGE fixed distance, date key, plain number",
        "SUM(V) OVER (ORDER BY D RANGE BETWEEN 7 PRECEDING AND CURRENT ROW)",
        (),
    ),
    (
        "EXCLUDE CURRENT ROW",
        f"SUM(V) OVER ({ORDER} ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING EXCLUDE CURRENT ROW)",
        (),
    ),
    (
        "EXCLUDE TIES",
        f"SUM(V) OVER ({ORDER} ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING EXCLUDE TIES)",
        (),
    ),
    ("GROUPS", f"SUM(V) OVER ({ORDER} GROUPS BETWEEN 1 PRECEDING AND 1 FOLLOWING)", ()),
    (
        "NULL ordering emulation",
        "ROW_NUMBER() OVER (ORDER BY CASE WHEN V IS NULL THEN 0 ELSE 1 END, V)",
        (),
    ),
    ("over a text column", f"LAG(S) OVER ({ORDER})", ()),
    ("over an NCLOB column", f"FIRST_VALUE(T) OVER ({ORDER})", ()),
)


def case(conn, results, key: str, sql: str, params=()) -> dict[str, Any]:
    """One statement; the rows, or its SQLSTATE and SQLCODE."""
    outcome = _query(conn, sql, params)
    return _step(
        results,
        key,
        {
            "sql": sql,
            "result": outcome["result"],
            **{k: v for k, v in outcome.items() if k != "result"},
        },
    )


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (a table gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _execute(
        conn,
        f"CREATE TABLE {TABLE} (I INTEGER, G INTEGER, V DOUBLE, D DATE, S NVARCHAR(50), T NCLOB)",
    )
    if created["result"] != "ok":
        return _step(results, "create", created) and results
    for row in ROWS:
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?, ?, ?)", [*row, row[4]])
    for key, expression, params in CASES:
        case(conn, results, key, f"SELECT I, {expression} FROM {TABLE} {ORDER}", params)
    case(
        conn,
        results,
        "window in a subquery, filtered outside (QUALIFY as Django writes it)",
        f"SELECT * FROM (SELECT I, ROW_NUMBER() OVER ({ORDER}) AS QUAL0 FROM {TABLE}) QUALIFY "
        "WHERE QUAL0 = ?",
        (2,),
    )
    case(
        conn,
        results,
        "window directly in WHERE",
        f"SELECT I FROM {TABLE} WHERE ROW_NUMBER() OVER ({ORDER}) = 1",
    )
    case(
        conn,
        results,
        "aggregate of an aggregate in GROUP BY",
        f"SELECT G, SUM(SUM(V)) OVER (ORDER BY G) FROM {TABLE} GROUP BY G ORDER BY G",
    )
    case(
        conn,
        results,
        "window in ORDER BY",
        f"SELECT I FROM {TABLE} ORDER BY ROW_NUMBER() OVER (ORDER BY I DESC)",
    )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
