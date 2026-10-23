"""Probe 20: a predicate as a three-valued selected value.

Read-only (VALUES only). Issue #75: a selected predicate is written as
``CASE WHEN p THEN TRUE ELSE FALSE END``, which turns UNKNOWN into FALSE. The
candidate form is ``CASE WHEN p THEN TRUE WHEN NOT (p) THEN FALSE END`` (NULL
otherwise). For each kind of predicate the backend produces, on rows with
NULLs, this probe compares the candidate (in the select list) and the rows of
``WHERE p`` / ``WHERE NOT (p)`` with the three-valued truth computed in
Python from the same rows. Db2 for i's NOT of a BOOLEAN *value* is two-valued
(probe ``queries``), so bare BOOLEAN values used as predicates are included,
as Django writes them for ``filter(flag=True/False)``, together with their
comparison forms. Predicates with subqueries (the IN rewrite, a correlated
sliced scalar subquery) are evaluated twice by the candidate. Findings go to
docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

NI, NB, NS = "CAST(NULL AS INTEGER)", "CAST(NULL AS BOOLEAN)", "CAST(NULL AS VARCHAR(10))"
TRUE, FALSE = "CAST(TRUE AS BOOLEAN)", "CAST(FALSE AS BOOLEAN)"
DATA = [  # K, X, V, S
    (1, 1, True, "ab"),
    (2, 5, False, "xy"),
    (3, None, None, None),
    (4, 2, None, "az"),
    (5, None, True, "ba"),
]


def _sql(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return TRUE if value else FALSE
    if isinstance(value, int):
        return str(value)
    return f"'{value}'"


ROWS = (
    "(VALUES "
    + ", ".join(
        f"({k}, {_sql(x) if x is not None else NI}, {_sql(v) if v is not None else NB}, "
        f"{_sql(s) if s is not None else NS})"
        for k, x, v, s in DATA
    )
    + ") T (K, X, V, S)"
)
# A subquery with a NULL (for the IN rewrite) and a sliced, correlated one.
SUB = f"SELECT Y FROM (VALUES 1, {NI}) Q (Y)"
LATERAL = f'LATERAL ({SUB}) AS "DJDB2I_IN" (V1)'
IN_REWRITE = (
    f'(CASE WHEN (SELECT 1 FROM {LATERAL} WHERE "DJDB2I_IN".V1 = T.X FETCH FIRST 1 ROWS ONLY) '
    f"IS NOT NULL THEN TRUE WHEN (SELECT 1 FROM {LATERAL} WHERE "
    '("DJDB2I_IN".V1 = T.X OR "DJDB2I_IN".V1 IS NULL OR T.X IS NULL) FETCH FIRST 1 ROWS ONLY) '
    "IS NOT NULL THEN NULL ELSE FALSE END) = TRUE"
)
SLICED_SCALAR = (
    "T.X > (SELECT Z FROM (VALUES 0, 1, 3) R (Z) WHERE R.Z < T.K ORDER BY Z DESC "
    "FETCH FIRST 1 ROWS ONLY)"
)


def _and(a, b):
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def _or(a, b):
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False


def _not(a):
    return None if a is None else not a


def _lt(a, b):
    return None if a is None or b is None else a < b


def _gt(a, b):
    return None if a is None or b is None else a > b


def _in_one_null(x):  # x IN (1, NULL)
    if x is None:
        return None
    return True if x == 1 else None


def _sliced(k, x):  # x > the largest of (0, 1, 3) below k
    below = [z for z in (0, 1, 3) if z < k]
    return _gt(x, max(below)) if below else None


def _starts_a(s):
    return None if s is None else s.startswith("a")


# (label, predicate SQL, params of one predicate, truth per row (k, x, v, s))
PREDICATES: list[tuple[str, str, tuple, Any]] = [
    ("X < ? (untyped marker)", "T.X < ?", (2,), lambda k, x, v, s: _lt(x, 2)),
    ("X < CAST(? AS INTEGER)", "T.X < CAST(? AS INTEGER)", (2,), lambda k, x, v, s: _lt(x, 2)),
    ("bare BOOLEAN value V (Django: filter(flag=True))", "T.V", (), lambda k, x, v, s: v),
    ("NOT V (Django: filter(flag=False))", "NOT T.V", (), lambda k, x, v, s: _not(v)),
    ("V = TRUE", "T.V = TRUE", (), lambda k, x, v, s: v),
    ("V = FALSE", "T.V = FALSE", (), lambda k, x, v, s: _not(v)),
    (
        "NegatedValue CASE as a condition",
        "CASE T.V WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END",
        (),
        lambda k, x, v, s: _not(v),
    ),
    (
        "NegatedValue CASE = TRUE",
        "(CASE T.V WHEN TRUE THEN FALSE WHEN FALSE THEN TRUE END) = TRUE",
        (),
        lambda k, x, v, s: _not(v),
    ),
    ("X < 2 AND V = TRUE", "T.X < 2 AND T.V = TRUE", (), lambda k, x, v, s: _and(_lt(x, 2), v)),
    (
        "X < 2 OR S LIKE 'a%'",
        "T.X < 2 OR T.S LIKE 'a%'",
        (),
        lambda k, x, v, s: _or(_lt(x, 2), _starts_a(s)),
    ),
    ("IN rewrite (subquery with NULL)", IN_REWRITE, (), lambda k, x, v, s: _in_one_null(x)),
    (
        "row value (X, S) = (?, ?)",
        "(T.X, T.S) = (?, ?)",
        (1, "ab"),
        lambda k, x, v, s: _and(None if x is None else x == 1, None if s is None else s == "ab"),
    ),
    ("correlated sliced scalar subquery", SLICED_SCALAR, (), lambda k, x, v, s: _sliced(k, x)),
    (
        "REGEXP_LIKE(S, ?)",
        "REGEXP_LIKE(T.S, CAST(? AS NVARCHAR(32)))",
        ("^a",),
        lambda k, x, v, s: _starts_a(s),
    ),
]

_SQLCODE = re.compile(r"\((-?\d+)\)")


def fetch(conn, sql: str, params: tuple) -> Any:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return [tuple(row) for row in cursor.fetchall()]
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        return f"error {code.group(1) if code else exc.args[0]}"
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, p, params, truth in PREDICATES:
        want = [(k, truth(k, x, v, s)) for k, x, v, s in DATA]
        form = f"CASE WHEN {p} THEN TRUE WHEN NOT ({p}) THEN FALSE END"
        selected = fetch(conn, f"SELECT K, {form} FROM {ROWS} ORDER BY K", params + params)
        where = fetch(conn, f"SELECT K FROM {ROWS} WHERE {p} ORDER BY K", params)
        where_not = fetch(conn, f"SELECT K FROM {ROWS} WHERE NOT ({p}) ORDER BY K", params)
        want_where = [(k,) for k, t in want if t is True]
        want_not = [(k,) for k, t in want if t is False]
        outcome = {
            "selected (candidate)": f"{selected}",
            "three-valued truth": f"{want}",
            "WHERE p / NOT (p)": f"{where} / {where_not}",
            "verdict selected": "same" if selected == want else "DIFFERENT",
            "verdict WHERE": "same"
            if where == want_where and where_not == want_not
            else f"DIFFERENT (want {want_where} / {want_not})",
        }
        results[label] = outcome
        print(f"\n  {label}")
        for key, value in outcome.items():
            print(f"    {key:<22} {value}")
    return results
