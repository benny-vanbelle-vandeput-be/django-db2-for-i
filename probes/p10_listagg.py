"""Probe 10: LISTAGG, for Django's StringAgg (aggregation module).

Read-only: VALUES and a recursive common table expression only. Records the
result type (from the cursor description) and length, and what happens when
the aggregated string exceeds LISTAGG's maximum length: an error, or
truncation. Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

_SQLCODE = re.compile(r"\((-?\d+)\)")


def rows(n: int) -> str:
    """A table R (N) with the rows 1 .. n."""
    return f"WITH R (N) AS (VALUES 1 UNION ALL SELECT N + 1 FROM R WHERE N < {n}) "


def listagg(argument: str, n: int, separator: str = "','") -> str:
    return f"{rows(n)}SELECT LISTAGG({argument}, {separator}) FROM R"


def measured(argument: str, n: int, separator: str = "','") -> str:
    return f"{rows(n)}SELECT LENGTH(LISTAGG({argument}, {separator})) FROM R"


# LISTAGG that is fetched as NULL over no values (see the "no rows" checks).
NULL_SAFE = (
    "CASE WHEN COUNT(CAST(VARCHAR(N) AS NCLOB(1K))) = 0 THEN NULL ELSE "
    "LISTAGG(CAST(VARCHAR(N) AS NCLOB(1K)), CAST(? AS NVARCHAR(32))) END"
)

# (label, sql, params)
CHECKS: list[tuple[str, str, tuple]] = [
    ("type: VARCHAR argument", listagg("VARCHAR(N)", 3), ()),
    ("type: NVARCHAR argument", listagg("CAST(N AS NVARCHAR(10))", 3), ()),
    (
        "type: NVARCHAR argument, typed NVARCHAR separator",
        listagg("CAST(N AS NVARCHAR(10))", 3, "CAST(? AS NVARCHAR(32))"),
        (", ",),
    ),
    ("type: NCLOB argument", listagg("CAST(N AS NCLOB(1K))", 3), ()),
    ("type: CLOB argument", listagg("CAST(N AS CLOB(1K))", 3), ()),
    ("non-ASCII marker", listagg("CAST(? AS NVARCHAR(10))", 2), ("é€",)),
    ("NULL values are skipped", listagg("CASE WHEN N = 2 THEN NULL ELSE VARCHAR(N) END", 3), ()),
    ("no rows", f"{rows(3)}SELECT LISTAGG(VARCHAR(N), ',') FROM R WHERE N > 9", ()),
    (
        "no rows: IS NULL",
        f"{rows(3)}SELECT CASE WHEN LISTAGG(VARCHAR(N), ',') IS NULL THEN 'null' ELSE 'not null' "
        "END FROM R WHERE N > 9",
        (),
    ),
    (
        "no rows, NCLOB: IS NULL",
        f"{rows(3)}SELECT CASE WHEN LISTAGG(CAST(VARCHAR(N) AS NCLOB(1K)), "
        "CAST(? AS NVARCHAR(32))) IS NULL THEN 'null' ELSE 'not null' END FROM R WHERE N > 9",
        (",",),
    ),
    (
        "no rows, NCLOB: LENGTH",
        f"{rows(3)}SELECT LENGTH(LISTAGG(CAST(VARCHAR(N) AS NCLOB(1K)), "
        "CAST(? AS NVARCHAR(32)))) FROM R WHERE N > 9",
        (",",),
    ),
    (
        "only NULL values: IS NULL",
        f"{rows(3)}SELECT CASE WHEN LISTAGG(CAST(NULL AS VARCHAR(1)), ',') IS NULL THEN 'null' "
        "ELSE 'not null' END FROM R",
        (),
    ),
    (
        "no rows, grouped: IS NULL",
        f"{rows(3)}SELECT CASE WHEN LISTAGG(VARCHAR(N), ',') IS NULL THEN 'null' ELSE 'not null' "
        "END FROM R WHERE N > 9 GROUP BY N",
        (),
    ),
    (
        "no rows: COALESCE",
        f"{rows(3)}SELECT COALESCE(LISTAGG(VARCHAR(N), ','), 'default') FROM R WHERE N > 9",
        (),
    ),
    (
        "no rows, NCLOB argument: fetched",
        f"{rows(3)}SELECT LISTAGG(CAST(VARCHAR(N) AS NCLOB(1K)), CAST(? AS NVARCHAR(32))) "
        "FROM R WHERE N > 9",
        (",",),
    ),
    (
        "no rows, fetched as CAST(... AS NCLOB(1M))",
        f"{rows(3)}SELECT CAST(LISTAGG(CAST(VARCHAR(N) AS NCLOB(1K)), CAST(? AS NVARCHAR(32))) "
        "AS NCLOB(1M)) FROM R WHERE N > 9",
        (",",),
    ),
    (
        "no rows, fetched from a derived table",
        f"{rows(3)}SELECT T.L FROM (SELECT LISTAGG(CAST(VARCHAR(N) AS NCLOB(1K)), "
        "CAST(? AS NVARCHAR(32))) AS L FROM R WHERE N > 9) T",
        (",",),
    ),
    (
        "no rows, fetched with a second NULL column",
        f"{rows(3)}SELECT LISTAGG(VARCHAR(N), ','), MAX(N) FROM R WHERE N > 9",
        (),
    ),
    (
        "no rows, fetched with a second non-NULL column",
        f"{rows(3)}SELECT LISTAGG(VARCHAR(N), ','), COUNT(*) FROM R WHERE N > 9",
        (),
    ),
    (
        "no rows, fetched second of two columns",
        f"{rows(3)}SELECT COUNT(*), LISTAGG(VARCHAR(N), ',') FROM R WHERE N > 9",
        (),
    ),
    ("no rows, MAX alone: fetched", f"{rows(3)}SELECT MAX(VARCHAR(N)) FROM R WHERE N > 9", ()),
    ("only NULL values: fetched", listagg("CAST(NULL AS VARCHAR(1))", 3), ()),
    (
        "no rows, NULLIF(..., ''): fetched",
        f"{rows(3)}SELECT NULLIF(LISTAGG(VARCHAR(N), ','), '') FROM R WHERE N > 9",
        (),
    ),
    (
        "no rows, CASE WHEN COUNT(arg) = 0: fetched",
        f"{rows(3)}SELECT {NULL_SAFE} FROM R WHERE N > 9",
        (",",),
    ),
    (
        "rows, CASE WHEN COUNT(arg) = 0: fetched",
        f"{rows(3)}SELECT {NULL_SAFE} FROM R",
        (",",),
    ),
    (
        "one empty string: fetched",
        listagg("CAST('' AS VARCHAR(1))", 1),
        (),
    ),
    (
        "one empty string: IS NULL",
        f"{rows(1)}SELECT CASE WHEN LISTAGG(CAST('' AS VARCHAR(1)), ',') IS NULL THEN 'null' "
        "ELSE 'not null' END FROM R",
        (),
    ),
    ("DISTINCT", listagg("DISTINCT VARCHAR(MOD(N, 2))", 4), ()),
    (
        "WITHIN GROUP (ORDER BY ... DESC)",
        f"{rows(3)}SELECT LISTAGG(VARCHAR(N), ',') WITHIN GROUP (ORDER BY N DESC) FROM R",
        (),
    ),
    (
        "ON OVERFLOW TRUNCATE",
        f"{rows(3)}SELECT LISTAGG(VARCHAR(N), ',' ON OVERFLOW TRUNCATE) FROM R",
        (),
    ),
    (
        "ON OVERFLOW ERROR",
        f"{rows(3)}SELECT LISTAGG(VARCHAR(N), ',' ON OVERFLOW ERROR) FROM R",
        (),
    ),
    # Length limits: 1000-character values, n rows (+ n - 1 separators).
    ("VARCHAR 1000 x 4 (4003)", measured("CAST(REPEAT('x', 1000) AS VARCHAR(1000))", 4), ()),
    ("VARCHAR 1000 x 32 (32031)", measured("CAST(REPEAT('x', 1000) AS VARCHAR(1000))", 32), ()),
    ("VARCHAR 1000 x 33 (33032)", measured("CAST(REPEAT('x', 1000) AS VARCHAR(1000))", 33), ()),
    ("NVARCHAR 1000 x 4 (4003)", measured("CAST(REPEAT('x', 1000) AS NVARCHAR(1000))", 4), ()),
    ("NVARCHAR 1000 x 16 (16015)", measured("CAST(REPEAT('x', 1000) AS NVARCHAR(1000))", 16), ()),
    ("NVARCHAR 1000 x 17 (17016)", measured("CAST(REPEAT('x', 1000) AS NVARCHAR(1000))", 17), ()),
    ("NVARCHAR 1000 x 40 (40039)", measured("CAST(REPEAT('x', 1000) AS NVARCHAR(1000))", 40), ()),
    (
        "NVARCHAR 1000 x 17, fetched",
        listagg("CAST(REPEAT('x', 1000) AS NVARCHAR(1000))", 17),
        (),
    ),
    (
        "NVARCHAR 1000 x 17, typed separator, fetched",
        listagg("CAST(REPEAT('x', 1000) AS NVARCHAR(1000))", 17, "CAST(? AS NVARCHAR(32))"),
        (",",),
    ),
    (
        "VARCHAR 1000 x 5, ON OVERFLOW TRUNCATE",
        listagg("CAST(REPEAT('x', 1000) AS VARCHAR(1000))", 5, "',' ON OVERFLOW TRUNCATE"),
        (),
    ),
    (
        "VARCHAR 1000 x 5, ON OVERFLOW TRUNCATE, tail",
        f"{rows(5)}SELECT RIGHT(LISTAGG(CAST(REPEAT('x', 1000) AS VARCHAR(1000)), ',' "
        "ON OVERFLOW TRUNCATE), 30) FROM R",
        (),
    ),
    ("NCLOB 1000 x 40 (40039)", measured("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 40), ()),
    ("NCLOB 1000 x 17, fetched", listagg("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 17), ()),
    (
        "NCLOB 1000 x 17, typed separator, fetched",
        listagg("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 17, "CAST(? AS NVARCHAR(32))"),
        (",",),
    ),
    ("NCLOB 1000 x 1048 (1049047)", measured("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 1048), ()),
    ("NCLOB 1000 x 1049 (1050048)", measured("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 1049), ()),
    ("NCLOB 1000 x 524 (524523)", measured("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 524), ()),
    ("NCLOB 1000 x 525 (525524)", measured("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 525), ()),
    ("NCLOB 1000 x 1000 (1000999)", measured("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 1000), ()),
    ("NCLOB(2K) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(2K))", 3), ()),
    ("NCLOB(4K) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(4K))", 3), ()),
    ("NCLOB(8K) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(8K))", 3), ()),
    (
        "NCLOB(16370) argument, typed NVARCHAR separator",
        listagg("CAST(VARCHAR(N) AS NCLOB(16370))", 3, "CAST(? AS NVARCHAR(32))"),
        (",",),
    ),
    (
        "NCLOB(1M) argument, typed NVARCHAR separator",
        listagg("CAST(VARCHAR(N) AS NCLOB(1M))", 3, "CAST(? AS NVARCHAR(32))"),
        (",",),
    ),
    (
        "NCLOB 1000 x 1048 (1049047), typed separator",
        measured("CAST(REPEAT('x', 1000) AS NCLOB(1K))", 1048, "CAST(? AS NVARCHAR(32))"),
        (",",),
    ),
    (
        "NCLOB 1000 x 1048, ON OVERFLOW TRUNCATE",
        f"{rows(1048)}SELECT LENGTH(LISTAGG(CAST(REPEAT('x', 1000) AS NCLOB(1K)), ',' "
        "ON OVERFLOW TRUNCATE)) FROM R",
        (),
    ),
    ("NCLOB(16370) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(16370))", 3), ()),
    ("NCLOB(256K) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(256K))", 3), ()),
    ("NCLOB(512K) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(512K))", 3), ()),
    ("NCLOB(1M) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(1M))", 3), ()),
    ("NCLOB(2M) argument: type", listagg("CAST(VARCHAR(N) AS NCLOB(2M))", 3), ()),
    ("NCLOB argument: DISTINCT", listagg("DISTINCT CAST(VARCHAR(MOD(N, 2)) AS NCLOB(1K))", 4), ()),
    (
        "NCLOB argument: WITHIN GROUP",
        f"{rows(3)}SELECT LISTAGG(CAST(VARCHAR(N) AS NCLOB(1K)), ',') "
        "WITHIN GROUP (ORDER BY N DESC) FROM R",
        (),
    ),
    (
        "NCLOB 1000 x 525, ON OVERFLOW TRUNCATE",
        f"{rows(525)}SELECT LENGTH(LISTAGG(CAST(REPEAT('x', 1000) AS NCLOB(1K)), ',' "
        "ON OVERFLOW TRUNCATE)) FROM R",
        (),
    ),
    ("non-ASCII marker, NCLOB", listagg("CAST(CAST(? AS NVARCHAR(10)) AS NCLOB(1K))", 2), ("é€",)),
]


def attempt(conn, sql: str, params: tuple) -> tuple[bool, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        description = cursor.description[0]
        rows = [tuple(row) for row in cursor.fetchall()]
        value = rows[0][0] if rows else None
        if isinstance(value, str) and len(value) > 40:
            value = f"<str of {len(value)} characters>"
        type_name = getattr(description[1], "__name__", description[1])
        return True, f"{value!r} (type {type_name}, size {description[3]})"
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        text = re.sub(r"^(\[[^\]]*\]\s*)+", "", message)
        return False, f"{code.group(1) if code else exc.args[0]}: {text[:110]}"
    finally:
        cursor.close()


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, sql, params in CHECKS:
        ok, detail = attempt(conn, sql, params)
        line = f"ok: {detail}" if ok else f"error {detail}"
        results[label] = line
        print(f"  {label:<48} {line}")
    return results
