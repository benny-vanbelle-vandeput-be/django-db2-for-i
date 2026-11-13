"""Chr and Ord above U+FFFF through UTF-16 surrogate pairs (#252, decision 3).

``qtemp_phase7_flags`` showed that ``INTERPRET(... AS GRAPHIC(1) CCSID 1200)`` gives
``Chr`` and ``Ord`` for the Basic Multilingual Plane. A code point above U+FFFF is two
UTF-16 code units, a surrogate pair::

    high = 0xD800 + (cp - 0x10000) / 1024      (55296 + ...)
    low  = 0xDC00 + MOD(cp - 0x10000, 1024)    (56320 + ...)

This probe builds the pair in SQL and interprets it as ``GRAPHIC(2) CCSID 1200``
(``Chr``), and the reverse for ``Ord``: the first two code units of the string, combined
when the first one is a high surrogate. Each form is tried on parameters (Django's
``Value``) and on column values (``NVARCHAR`` and ``NCLOB``, the backend's types for
``CharField`` and ``TextField``), and the value that comes back is compared with Python's
``chr()`` / ``ord()``.

QTEMP only: one table, gone with the job. Without commitment control. One connection,
no retries. Each statement's rows, or its SQLSTATE and SQLCODE, are recorded.

Usage (inside the "tests" container):
    nox -s probe -- supplementary_chars

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import ast
from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

DUMMY = "FROM SYSIBM.SYSDUMMY1"
TABLE = "QTEMP.PSUPCH"

CODE_POINTS = (65, 233, 8364, 0xFFFD, 0x10000, 0x1F600, 0x10FFFF)
STRINGS = ("A", "é", "€", "\U0001f600", "\U0001f600x", "x\U0001f600", "\U0010ffff", "")


def _int(x: str) -> str:
    return f"CAST({x} AS INTEGER)"


def chr_bmp(x: str) -> str:
    """The form from qtemp_phase7_flags: one code unit."""
    return f"INTERPRET(HEXTORAW(RIGHT(HEX({_int(x)}), 4)) AS GRAPHIC(1) CCSID 1200)"


def chr_pair(x: str) -> str:
    """Two code units: the surrogate pair."""
    high = f"RIGHT(HEX(55296 + ({_int(x)} - 65536) / 1024), 4)"
    low = f"RIGHT(HEX(56320 + MOD({_int(x)} - 65536, 1024)), 4)"
    return f"INTERPRET(HEXTORAW({high} CONCAT {low}) AS GRAPHIC(2) CCSID 1200)"


def chr_case(x: str) -> str:
    """Either, as one VARGRAPHIC: no padding blank after a BMP character."""
    return (
        f"CASE WHEN {_int(x)} < 65536 "
        f"THEN CAST({chr_bmp(x)} AS VARGRAPHIC(2) CCSID 1200) "
        f"ELSE CAST({chr_pair(x)} AS VARGRAPHIC(2) CCSID 1200) END"
    )


def chr_vargraphic(x: str) -> str:
    """One INTERPRET of 2 or 4 bytes as VARGRAPHIC (does INTERPRET take the length?)."""
    pair = (
        f"RIGHT(HEX(55296 + ({_int(x)} - 65536) / 1024), 4) CONCAT "
        f"RIGHT(HEX(56320 + MOD({_int(x)} - 65536, 1024)), 4)"
    )
    hexed = f"CASE WHEN {_int(x)} < 65536 THEN RIGHT(HEX({_int(x)}), 4) ELSE {pair} END"
    return f"INTERPRET(HEXTORAW({hexed}) AS VARGRAPHIC(2) CCSID 1200)"


def _hex2(s: str) -> str:
    """HEX of the string's first two code units. A CAST to VARGRAPHIC(2) keeps exactly
    those, also for an NCLOB, where SUBSTR and LEFT pad with blanks (see "nclob: ...")."""
    return f"HEX(CAST({s} AS VARGRAPHIC(2) CCSID 1200))"


def _unit(s: str, n: int) -> str:
    return f"INTERPRET(HEXTORAW('0000' CONCAT SUBSTR({_hex2(s)}, {4 * n - 3}, 4)) AS INTEGER)"


def ord_units(s: str) -> str:
    u1, u2 = _unit(s, 1), _unit(s, 2)
    return (
        f"CASE WHEN LENGTH({s}) = 0 THEN 0 "
        f"WHEN {u1} BETWEEN 55296 AND 56319 THEN ({u1} - 55296) * 1024 + ({u2} - 56320) + 65536 "
        f"ELSE {u1} END"
    )


def _param_string() -> str:
    return "CAST(? AS VARGRAPHIC(100) CCSID 1200)"


def _compare(results, key, outcome, expected) -> None:
    rows = outcome.get("rows") if isinstance(outcome, dict) else None
    if rows:
        outcome["expected"] = expected
        outcome["matches"] = ast.literal_eval(rows[0][0]) == expected
    _step(results, key, outcome)


def _one(conn, results, key: str, sql: str, params, expected) -> None:
    outcome = _query(conn, sql, params)
    _compare(results, key, {"sql": sql, **outcome}, expected)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": f"QTEMP only ({TABLE}, gone with the job)"}

    # Chr of a parameter, each form.
    for name, form in (
        ("bmp", chr_bmp),
        ("pair", chr_pair),
        ("case", chr_case),
        ("vargraphic", chr_vargraphic),
    ):
        for cp in CODE_POINTS:
            if name == "pair" and cp < 0x10000:
                continue
            _one(
                conn,
                results,
                f"chr {name}: parameter {cp:#x}",
                f"SELECT {form('?')}, HEX({form('?')}) {DUMMY}",
                (cp,) * (2 * form("?").count("?")),
                chr(cp),
            )

    # Ord of a parameter.
    for s in (*STRINGS, None):
        expected = ord(s[0]) if s else (0 if s == "" else None)
        sql = f"SELECT {ord_units(_param_string())} {DUMMY}"
        _one(conn, results, f"ord: parameter {s!r}", sql, (s,) * sql.count("?"), expected)

    # Column values: NVARCHAR and NCLOB, as CharField and TextField.
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _execute(
        conn,
        f"CREATE TABLE {TABLE} (ID INTEGER, CP INTEGER, S NVARCHAR(10), T NCLOB(1K))",
    )
    _step(results, "create table", created)
    if created["result"] != "ok":
        return results
    rows = [(i, cp, chr(cp), chr(cp)) for i, cp in enumerate(CODE_POINTS)]
    rows += [(100 + i, None, s, s) for i, s in enumerate(STRINGS)]
    for row in rows:
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?)", row)

    outcome = _query(
        conn,
        f"SELECT ID, CP, {chr_case('CP')}, HEX({chr_case('CP')}) FROM {TABLE} "
        "WHERE CP IS NOT NULL ORDER BY ID",
    )
    if outcome.get("rows"):
        values = [[ast.literal_eval(v) for v in r] for r in outcome["rows"]]
        outcome["matches"] = all(r[2] == chr(r[1]) for r in values)
    _step(results, "chr case: column CP", {"sql": "chr_case(CP)", **outcome})

    outcome = _query(
        conn,
        f"SELECT COUNT(*) FROM {TABLE} WHERE CP IS NOT NULL AND S = {chr_case('CP')}",
    )
    _step(results, "chr case: equal to the stored NVARCHAR", outcome)

    for column in ("S", "T"):
        outcome = _query(conn, f"SELECT ID, {column}, {ord_units(column)} FROM {TABLE} ORDER BY ID")
        if outcome.get("rows"):
            values = [[ast.literal_eval(v) for v in r] for r in outcome["rows"]]
            outcome["matches"] = all(r[2] == (ord(r[1][0]) if r[1] else 0) for r in values)
        _step(results, f"ord: column {column}", {"sql": f"ord_units({column})", **outcome})

    for column in ("S", "T"):  # what SUBSTR(..., 1, 2) returns for 'x' + an emoji
        _step(
            results,
            f"substr: column {column}",
            _query(
                conn,
                f"SELECT ID, LENGTH({column}), HEX(SUBSTR({column}, 1, 2)) FROM {TABLE} "
                "WHERE ID IN (5, 104, 105) ORDER BY ID",
            ),
        )

    # NCLOB: SUBSTR(T, 1, 2) is not two code units; other ways to the first two.
    for name, first_two in (
        ("SUBSTRING CODEUNITS16", "SUBSTRING(T, 1, 2, CODEUNITS16)"),
        ("SUBSTRING OCTETS", "SUBSTRING(T, 1, 4, OCTETS)"),
        ("LEFT", "LEFT(T, 2)"),
        ("SUBSTR 1", "SUBSTR(T, 1, 1)"),
        ("CAST VARGRAPHIC(2)", "CAST(T AS VARGRAPHIC(2) CCSID 1200)"),
        ("CAST SUBSTR VARGRAPHIC", "CAST(SUBSTR(T, 1, 2) AS VARGRAPHIC(2) CCSID 1200)"),
    ):
        _step(
            results,
            f"nclob: {name}",
            _query(
                conn,
                f"SELECT ID, HEX(CAST({first_two} AS VARGRAPHIC(4) CCSID 1200)) FROM {TABLE} "
                "WHERE ID IN (0, 5, 104, 105, 107) ORDER BY ID",
            ),
        )

    _execute(conn, f"DROP TABLE {TABLE}")
    return results
