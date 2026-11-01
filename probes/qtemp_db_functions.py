"""Django's database functions as Django writes them, for phase 6
(``tests/db_functions``, ``rounds_to_even``, ``supports_cast_with_precision``).

Writes only to QTEMP (a table that disappears with the job); reads nothing
outside it but SYSIBM.SYSDUMMY1. Without commitment control (CMT=0). One
connection, one statement per case, no retries. Each case has Django's default
SQL where it differs from what Db2 for i is expected to take; the outcome tells
which functions need an ``as_db2_for_i``. The values matter too: NULL arguments,
non-ASCII text and how hashes are encoded.

Usage (inside the "tests" container):
    nox -s probe -- db_functions

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

TABLE = "QTEMP.P6FN"
TEXT = "héllo \U0001f600"
UTF8 = "CAST(S AS VARCHAR(100) CCSID 1208)"

# Each: an expression over S (NVARCHAR), N (NVARCHAR, NULL), I (INTEGER), D (DOUBLE),
# P (DECIMAL(9, 2)), with its markers. One row: (TEXT, NULL, 7, 2.5, 2.50).
CASES: tuple[tuple[str, tuple[Any, ...]], ...] = (
    # Text: Django's defaults, then the forms Db2 for i documents.
    ("CHR(65)", ()),
    ("CHR(233)", ()),
    ("CHR(128512)", ()),
    ("ASCII(S)", ()),
    ("UNICODE(S)", ()),
    ("CONCAT(S, N)", ()),
    ("CONCAT(S, 'x')", ()),
    ("CONCAT(S, CAST(? AS NVARCHAR(10)))", ("x",)),
    ("CONCAT(S, 'x', 'y')", ()),
    ("S || COALESCE(N, '')", ()),
    ("LEFT(S, 2)", ()),
    ("LEFT(S, ?)", (2,)),
    ("RIGHT(S, 2)", ()),
    ("RIGHT(S, ?)", (2,)),
    ("LENGTH(S)", ()),
    ("CHARACTER_LENGTH(S)", ()),
    ("CHAR_LENGTH(S)", ()),
    ("LOWER(S)", ()),
    ("UPPER(S)", ()),
    ("LPAD(S, 12, 'x')", ()),
    ("LPAD(S, ?, CAST(? AS NVARCHAR(10)))", (12, "x")),
    ("LPAD(S, 2, 'x')", ()),
    ("RPAD(S, 12, 'x')", ()),
    ("LTRIM(' a ')", ()),
    ("RTRIM(' a ')", ()),
    ("TRIM(' a ')", ()),
    ("REPEAT(S, 2)", ()),
    ("REPEAT(S, ?)", (2,)),
    ("REPEAT(S, CAST(NULL AS INTEGER))", ()),
    ("REPLACE(S, 'l', 'L')", ()),
    ("REPLACE(S, CAST(? AS NVARCHAR(10)), CAST(? AS NVARCHAR(10)))", ("l", "L")),
    ("REPLACE(S, 'l', '')", ()),
    ("REVERSE(S)", ()),
    ("INSTR(S, 'l')", ()),
    ("INSTR(S, CAST(? AS NVARCHAR(10)))", ("l",)),
    ("LOCATE('l', S)", ()),
    ("POSITION('l' IN S)", ()),
    ("SUBSTRING(S, 2, 2)", ()),
    ("SUBSTRING(S, ?, ?)", (2, 2)),
    ("SUBSTR(S, 2, 2)", ()),
    ("SUBSTRING(S, 2)", ()),
    # Hashes: Django's MD5, SHA1, ... take text and give lower-case hex.
    ("MD5(S)", ()),
    (f"LOWER(HEX(HASH_MD5({UTF8})))", ()),
    (f"LOWER(HEX(HASH_SHA1({UTF8})))", ()),
    (f"LOWER(HEX(HASH_SHA256({UTF8})))", ()),
    (f"LOWER(HEX(HASH_SHA512({UTF8})))", ()),
    (f"LOWER(HEX(HASH({UTF8}, 0)))", ()),
    (f"LOWER(HEX(HASH({UTF8}, 3)))", ()),
    (f"LOWER(HEX(HASH_SHA224({UTF8})))", ()),
    (f"LOWER(HEX(HASH_SHA384({UTF8})))", ()),
    ("LOWER(HEX(HASH_MD5(S)))", ()),
    ("LOWER(HEX(HASH_MD5(CAST(N AS VARCHAR(100) CCSID 1208))))", ()),
    # Comparison.
    ("COALESCE(N, S)", ()),
    ("COALESCE(N, CAST(? AS NVARCHAR(10)))", ("x",)),
    ("GREATEST(I, 9)", ()),
    ("LEAST(I, 9)", ()),
    ("MAX(I, 9)", ()),
    ("MIN(I, 9)", ()),
    ("MAX(I, CAST(NULL AS INTEGER))", ()),
    ("MAX(S, 'z')", ()),
    ("NULLIF(I, 7)", ()),
    ("NULLIF(S, CAST(? AS NVARCHAR(10)))", ("x",)),
    # Cast with a precision: does it round or cut off?
    ("CAST(P AS DECIMAL(9, 1))", ()),
    ("CAST(2.55 AS DECIMAL(9, 1))", ()),
    ("CAST(D AS DECIMAL(9, 0))", ()),
    ("CAST(3.7 AS INTEGER)", ()),
    ("CAST(S AS NVARCHAR(2))", ()),
    # Math.
    ("ABS(I)", ()),
    ("ACOS(0.5)", ()),
    ("ASIN(0.5)", ()),
    ("ATAN(0.5)", ()),
    ("ATAN2(1, 2)", ()),
    ("CEILING(D)", ()),
    ("COS(0.5)", ()),
    ("COT(0.5)", ()),
    ("DEGREES(1)", ()),
    ("EXP(1)", ()),
    ("FLOOR(D)", ()),
    ("LN(2)", ()),
    ("LOG(2, 8)", ()),
    ("LOG10(100)", ()),
    ("MOD(I, 3)", ()),
    ("MOD(D, 2)", ()),
    ("MOD(7.5, 2)", ()),
    ("PI()", ()),
    ("POWER(2, 3)", ()),
    ("POWER(D, 2)", ()),
    ("RADIANS(180)", ()),
    ("RAND()", ()),
    ("RANDOM()", ()),
    ("SIGN(I)", ()),
    ("SIN(0.5)", ()),
    ("SQRT(4)", ()),
    ("TAN(0.5)", ()),
    # Round: halves, on DOUBLE and DECIMAL, with and without the precision.
    ("ROUND(D)", ()),
    ("ROUND(D, 0)", ()),
    ("ROUND(P, 0)", ()),
    ("ROUND(3.5, 0)", ()),
    ("ROUND(CAST(3.5 AS DOUBLE), 0)", ()),
    ("ROUND(CAST(0.5 AS DOUBLE), 0)", ()),
    ("ROUND(CAST(-2.5 AS DOUBLE), 0)", ()),
    ("ROUND(D, ?)", (0,)),
    ("ROUND(D, CAST(? AS INTEGER))", (0,)),
    ("ROUND(CAST(12.345 AS DOUBLE), -1)", ()),
    # Date and time, what Django's Now writes.
    ("CURRENT_TIMESTAMP", ()),
    ("CURRENT TIMESTAMP(6)", ()),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (a table gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    columns = "S NVARCHAR(100), N NVARCHAR(100), I INTEGER, D DOUBLE, P DECIMAL(9, 2)"
    created = _execute(conn, f"CREATE TABLE {TABLE} ({columns})")
    results["create"] = created
    if created["result"] != "ok":
        return results
    _execute(conn, f"INSERT INTO {TABLE} VALUES (?, NULL, 7, 2.5, 2.50)", [TEXT])
    for expression, params in CASES:
        case(conn, results, expression, f"SELECT {expression} FROM {TABLE}", params)
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
