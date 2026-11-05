"""Forms of Django's database functions that ``qtemp_db_functions`` left open,
for phase 6 (PR 1, ``tests/db_functions``).

``qtemp_db_functions`` found that ``LEFT``, ``RIGHT``, ``REPEAT`` and
``SUBSTRING`` refuse a plain marker in a numeric argument; this backend writes
every ``Value`` as a typed marker, so this probe tries those. It also tries the
hashes on an ``NCLOB`` column and on text longer than 100 characters (a
``TextField``), ``CONCAT`` with ``COALESCE`` (Django's ``Concat`` treats NULL as
empty text), ``LN(b) / LN(a)`` for ``Log``, and ``ASCII`` on non-ASCII text
(Django's ``Ord``), and the forms of a rounded cast of a DOUBLE to
DECIMAL (Django's ``Cast`` with a precision rounds; Db2 for i's ``CAST`` cuts off).

Writes only to QTEMP (a table that disappears with the job); reads nothing
outside it. Without commitment control (CMT=0). One connection, one statement
per case, no retries.

Usage (inside the "tests" container):
    nox -s probe -- db_function_args

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.P6FA"
TEXT = "héllo \U0001f600"
LONG = "é" * 3000 + "\U0001f600"

# Each: an expression over S (NVARCHAR(100)), N (NVARCHAR(100), NULL), I (INTEGER),
# L (NCLOB), with its markers. One row: (TEXT, NULL, 2, LONG).
CASES: tuple[tuple[str, tuple[Any, ...]], ...] = (
    # Numeric arguments as typed markers and as columns.
    ("LEFT(S, CAST(? AS INTEGER))", (2,)),
    ("LEFT(S, I)", ()),
    ("RIGHT(S, CAST(? AS INTEGER))", (2,)),
    ("RIGHT(S, I)", ()),
    ("REPEAT(S, CAST(? AS INTEGER))", (2,)),
    ("REPEAT(S, I)", ()),
    ("SUBSTRING(S, CAST(? AS INTEGER), CAST(? AS INTEGER))", (2, 2)),
    ("SUBSTRING(S, CAST(? AS INTEGER))", (2,)),
    ("SUBSTRING(S, I, I)", ()),
    ("SUBSTR(S, CAST(? AS INTEGER), CAST(? AS INTEGER))", (2, 2)),
    ("LPAD(S, CAST(? AS INTEGER), CAST(? AS NVARCHAR(10)))", (12, "x")),
    ("LEFT(L, CAST(? AS INTEGER))", (2,)),
    ("SUBSTRING(L, CAST(? AS INTEGER), CAST(? AS INTEGER))", (2, 2)),
    # Concat: NULL as empty text.
    ("CONCAT(COALESCE(S, ''), COALESCE(N, ''))", ()),
    (
        "CONCAT(COALESCE(S, CAST(? AS NVARCHAR(10))), COALESCE(N, CAST(? AS NVARCHAR(10))))",
        ("", ""),
    ),
    ("CONCAT(COALESCE(L, ''), COALESCE(S, ''))", ()),
    # Log(a, b): the logarithm of b to base a.
    ("LN(8) / LN(2)", ()),
    ("LN(CAST(? AS DOUBLE)) / LN(CAST(? AS DOUBLE))", (8.0, 2.0)),
    # Ord on non-ASCII text.
    ("ASCII(CAST(? AS NVARCHAR(10)))", ("é",)),
    ("ASCII(CAST(? AS NVARCHAR(10)))", ("\U0001f600",)),
    # Hashes on long text and on an NCLOB.
    ("LOWER(HEX(HASH_MD5(CAST(S AS VARCHAR(32000) CCSID 1208))))", ()),
    ("LOWER(HEX(HASH_MD5(CAST(L AS VARCHAR(32000) CCSID 1208))))", ()),
    ("LOWER(HEX(HASH_MD5(CAST(L AS CLOB(2G) CCSID 1208))))", ()),
    ("LOWER(HEX(HASH_SHA256(CAST(L AS CLOB(2G) CCSID 1208))))", ()),
    ("LOWER(HEX(HASH_MD5(L)))", ()),
    ("LOWER(HEX(HASH_MD5(CAST(N AS CLOB(2G) CCSID 1208))))", ()),
    # Cast of a DOUBLE to DECIMAL(p, s), rounded (Django rounds; CAST cuts off).
    # D = -1.934, E = 3.467, H = 2.5, G = 1E20.
    ("CAST(ROUND(D, 2) AS DECIMAL(8, 2))", ()),
    ("CAST(ROUND(CAST(D AS DECFLOAT(34)), 2) AS DECIMAL(8, 2))", ()),
    ("CAST(ROUND(CAST(E AS DECFLOAT(34)), 1) AS DECIMAL(8, 1))", ()),
    ("CAST(ROUND(CAST(H AS DECFLOAT(34)), 0) AS DECIMAL(8, 0))", ()),
    ("CAST(ROUND(CAST(-H AS DECFLOAT(34)), 0) AS DECIMAL(8, 0))", ()),
    ("CAST(ROUND(CAST(G AS DECFLOAT(34)), 2) AS DECIMAL(31, 2))", ()),
    ("CAST(ROUND(CAST(D AS DECIMAL(63, 30)), 2) AS DECIMAL(8, 2))", ()),
    ("CAST(ROUND(CAST(H AS DECIMAL(63, 30)), 0) AS DECIMAL(8, 0))", ()),
    ("CAST(ROUND(CAST(G AS DECIMAL(63, 30)), 2) AS DECIMAL(31, 2))", ()),
    ("CAST(ROUND(CAST(2.555 AS DECIMAL(9, 3)), 2) AS DECIMAL(8, 2))", ()),
    ("CURRENT DECFLOAT ROUNDING MODE", ()),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (a table gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    columns = (
        "S NVARCHAR(100), N NVARCHAR(100), I INTEGER, L NCLOB(1M), "
        "D DOUBLE, E DOUBLE, H DOUBLE, G DOUBLE"
    )
    created = _execute(conn, f"CREATE TABLE {TABLE} ({columns})")
    results["create"] = created
    if created["result"] != "ok":
        return results
    _execute(
        conn,
        f"INSERT INTO {TABLE} VALUES (?, NULL, 2, ?, -1.934, 3.467, 2.5, 1E20)",
        [TEXT, LONG],
    )
    for expression, params in CASES:
        name = f"{expression} {params}" if params else expression
        case(conn, results, name, f"SELECT {expression} FROM {TABLE}", params)
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
