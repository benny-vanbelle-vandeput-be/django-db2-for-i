"""Forms of a cast of a DOUBLE to text, for phase 6 (``Cast(FloatField, CharField())``).

Db2 for i writes a DOUBLE cast to text in exponent notation (``3E0``,
``4.5E0``); Django's tests expect ``3`` and ``4.5``, as on its other backends
(``aggregation.tests.AggregateTestCase.test_distinct_on_stringagg``). This
probe tries the plain cast and the forms through ``DECFLOAT``, with and
without ``NORMALIZE_DECFLOAT``, ``VARCHAR`` and ``CHAR``, on whole numbers,
fractions that are and are not exact in binary, large and small exponents,
negatives and zero.

Writes only to QTEMP (a table that disappears with the job); reads nothing
outside it. Without commitment control (CMT=0). One connection, one statement
per case, no retries.

Usage (inside the "tests" container):
    nox -s probe -- float_text

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

TABLE = "QTEMP.P6FT"
VALUES = (
    3.0, 4.5, 0.1, 1 / 3, 300.0, 1e20, -2.5, 1.23e-7, 0.0, 123456789.125,
    10.0, 1e15, 1e16, 0.1 + 0.2, -0.0, 1e-5, 2.5e-300, 1.7976931348623157e308,
)  # fmt: skip

# Each an expression over D (DOUBLE); one row per value, ordered by K.
CASES: tuple[str, ...] = (
    "CAST(D AS NVARCHAR(100))",
    "VARCHAR(D)",
    "CHAR(D)",
    "CAST(CAST(D AS DECFLOAT(16)) AS NVARCHAR(100))",
    "CAST(CAST(D AS DECFLOAT(34)) AS NVARCHAR(100))",
    "CAST(NORMALIZE_DECFLOAT(CAST(D AS DECFLOAT(16))) AS NVARCHAR(100))",
    "CAST(NORMALIZE_DECFLOAT(CAST(D AS DECFLOAT(34))) AS NVARCHAR(100))",
    "VARCHAR_FORMAT(D)",
    "VARCHAR_FORMAT(CAST(D AS DECFLOAT(16)))",
    # Whole numbers without exponent: adding a DECFLOAT zero (exponent 0) or QUANTIZE.
    "CAST(CAST(D AS DECFLOAT(16)) + CAST(0 AS DECFLOAT(16)) AS NVARCHAR(100))",
    "CAST(CAST(D AS DECFLOAT(16)) + 0 AS NVARCHAR(100))",
    "CAST(CASE WHEN D = FLOOR(D) AND ABS(D) < 1E15 "
    "THEN QUANTIZE(CAST(D AS DECFLOAT(16)), DECFLOAT(0)) "
    "ELSE CAST(D AS DECFLOAT(16)) END AS NVARCHAR(100))",
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (a table gone with the job)", "values": VALUES}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _execute(conn, f"CREATE TABLE {TABLE} (K INTEGER, D DOUBLE)")
    results["create"] = created
    if created["result"] != "ok":
        return results
    for key, value in enumerate(VALUES):
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?)", [key, value])
    for expression in CASES:
        case(conn, results, expression, f"SELECT {expression} FROM {TABLE} ORDER BY K")
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
