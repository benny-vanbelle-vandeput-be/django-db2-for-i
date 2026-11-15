"""Scalars at the top level of a JSONField: a way around? (``supports_primitives_in_json_field``)

Probes ``json_functions`` and ``json_lookups`` found that Db2 for i's JSON
functions return NULL for ``$`` of a top-level number, string, ``true`` or
``null`` (and ``JSON_QUERY`` gives ``{}`` for a top-level ``null``), while
``$[1]`` of a top-level array works. So this probe wraps the column's text
before the JSON function reads it, and reads the value one level down:

- **array wrap:** ``'[' CONCAT C CONCAT ']'`` with the path ``$[0]...``;
- **object wrap:** ``'{"v":' CONCAT C CONCAT '}'`` with the path ``$.v...``.

On every kind of document (object, array, integer, decimal, string, ``true``,
``false``, JSON ``null``, SQL NULL) and with each wrap: ``JSON_QUERY`` (with and
without ``OMIT QUOTES``), ``JSON_VALUE`` as text and as ``DECFLOAT(34)``,
``JSON_EXISTS``, a key and an array position below the root, the path as a
parameter marker, and the exact comparison against the right-hand side the
backend writes now (``JSON_QUERY(JSON_OBJECT('value' VALUE ? FORMAT JSON),
'$.value')``). The unwrapped ``$`` forms run too, as the control.

Writes only to QTEMP (one table that disappears with the job); reads nothing
outside it but SYSIBM.SYSDUMMY1. Without commitment control (CMT=0). One connection, one statement
per case, no retries.

Usage (inside the "tests" container):
    nox -s probe -- json_primitives

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PJPRIM"
DOCUMENTS = (
    (1, '{"a": 1, "d": [10, 20], "s": "téxt"}'),
    (2, "[10, 20, 30]"),
    (3, "42"),
    (4, "1.5"),
    (5, '"téxt \U0001f600"'),
    (6, "true"),
    (7, "false"),
    (8, "null"),
    (9, None),
)
WRAPS = (
    ("none", "C", "$"),
    ("array", "('[' CONCAT C CONCAT ']')", "$[0]"),
    ("object", "('{\"v\":' CONCAT C CONCAT '}')", "$.v"),
)
RIGHT_HAND = (
    "JSON_QUERY(JSON_OBJECT('value' VALUE CAST(? AS NVARCHAR(4000)) FORMAT JSON), '$.value')"
)
EXACT_VALUES = ("42", "1.5", '"téxt \U0001f600"', "true", "false", "null", '{"a":1}')


def _forms(doc: str, root: str) -> tuple[tuple[str, str, tuple], ...]:
    return (
        ("JSON_QUERY", f"JSON_QUERY({doc}, '{root}')", ()),
        ("JSON_QUERY OMIT QUOTES", f"JSON_QUERY({doc}, '{root}' OMIT QUOTES)", ()),
        ("JSON_VALUE text", f"JSON_VALUE({doc}, '{root}' RETURNING NVARCHAR(4000))", ()),
        ("JSON_VALUE DECFLOAT", f"JSON_VALUE({doc}, '{root}' RETURNING DECFLOAT(34))", ()),
        ("JSON_EXISTS", f"CASE WHEN JSON_EXISTS({doc}, '{root}') THEN 1 ELSE 0 END", ()),
        ("key a", f"JSON_QUERY({doc}, '{root}.a')", ()),
        ("position 1", f"JSON_QUERY({doc}, '{root}[1]')", ()),
        ("path as a marker", f"JSON_QUERY({doc}, CAST(? AS VARCHAR(100)))", (root,)),
    )


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table, gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(
        results, "create", _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER, C NCLOB(1M))")
    )
    if created["result"] != "ok":
        return results
    for ident, text in DOCUMENTS:
        _step(
            results,
            f"insert {ident}",
            _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?)", [ident, text]),
        )
    for wrap, doc, root in WRAPS:
        print(f" -- wrap: {wrap}")
        for name, expression, params in _forms(doc, root):
            _step(
                results,
                f"{wrap}: {name}",
                _query(conn, f"SELECT ID, {expression} FROM {TABLE} ORDER BY ID", params),
            )
        for value in EXACT_VALUES:
            _step(
                results,
                f"{wrap}: exact {value}",
                _query(
                    conn,
                    f"SELECT ID FROM {TABLE} WHERE JSON_QUERY({doc}, '{root}') = {RIGHT_HAND} "
                    "ORDER BY ID",
                    (value,),
                ),
            )
    _step(
        results,
        "right-hand side of each exact value",
        _query(
            conn,
            "SELECT " + ", ".join(RIGHT_HAND for _ in EXACT_VALUES) + " FROM SYSIBM.SYSDUMMY1",
            EXACT_VALUES,
        ),
    )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
