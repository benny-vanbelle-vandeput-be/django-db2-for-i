"""The smaller flags that moved to phase 6.

Writes only to QTEMP (tables that disappear with the job); reads nothing outside
it. Without commitment control (CMT=0). One connection, no retries.

- ``allows_group_by_lob``: NCLOB and BLOB columns in GROUP BY, DISTINCT, ORDER BY.
- ``ignores_unnecessary_order_by_in_subqueries``: ORDER BY in a subquery.
- ``supports_aggregate_distinct_multiple_argument``: LISTAGG(DISTINCT ...) with a
  separator, as Django writes it.
- ``supports_no_precision_decimalfield``: how the driver can bind what a
  DECFLOAT(34) column takes (probe ``later_flags`` found ``1E+300`` refused at bind
  as a ``Decimal``, and values coming back as ``str``).
- ``has_real_datatype``: how the driver and the catalog describe REAL.

Usage (inside the "tests" container):
    nox -s probe -- phase6_flags

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step, connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.P6FLAG"
DECFLOATS = (
    ("a Decimal", Decimal("1E+300"), "?"),
    ("a typed Decimal marker", Decimal("1E+300"), "CAST(? AS DECFLOAT(34))"),
    ("a string", "1E+300", "?"),
    ("a typed string marker", "1E+300", "CAST(CAST(? AS VARCHAR(50)) AS DECFLOAT(34))"),
    ("34 digits as a Decimal", Decimal("1234567890123456789012345678901234"), "?"),
    (
        "34 digits as a string",
        "1234567890123456789012345678901234",
        "CAST(CAST(? AS VARCHAR(50)) AS DECFLOAT(34))",
    ),
    ("a small value as a Decimal", Decimal("1E-300"), "?"),
    ("a small value as a string", "1E-300", "CAST(CAST(? AS VARCHAR(50)) AS DECFLOAT(34))"),
    ("a float", 1e300, "?"),
    (
        "35 digits as a string",
        "12345678901234567890123456789012345",
        "CAST(CAST(? AS VARCHAR(50)) AS DECFLOAT(34))",
    ),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _execute(
        conn, f"CREATE TABLE {TABLE} (I INTEGER, T NCLOB, B BLOB(1M), S NVARCHAR(20), R REAL)"
    )
    results["create"] = created
    if created["result"] == "ok":
        _execute(
            conn,
            f"INSERT INTO {TABLE} (I, T, B, S, R) VALUES (1, 'a', NULL, 'x', 1.5), (2, 'a', NULL, "
            f"'y', 2.5), (3, 'b', NULL, 'x', 0.1)",
        )
        for key, sql in (
            ("GROUP BY an NCLOB", f"SELECT T, COUNT(*) FROM {TABLE} GROUP BY T"),
            ("GROUP BY a BLOB", f"SELECT B, COUNT(*) FROM {TABLE} GROUP BY B"),
            (
                "GROUP BY a cast NCLOB",
                f"SELECT CAST(T AS NVARCHAR(100)), COUNT(*) FROM {TABLE} GROUP BY CAST(T AS "
                f"NVARCHAR(100))",
            ),
            ("DISTINCT an NCLOB", f"SELECT DISTINCT T FROM {TABLE}"),
            ("ORDER BY an NCLOB", f"SELECT I FROM {TABLE} ORDER BY T"),
            (
                "ORDER BY in an IN subquery",
                f"SELECT I FROM {TABLE} WHERE I IN (SELECT I FROM {TABLE} ORDER BY I)",
            ),
            ("ORDER BY in a FROM subquery", f"SELECT I FROM (SELECT I FROM {TABLE} ORDER BY I) X"),
            (
                "ORDER BY in an EXISTS subquery",
                f"SELECT I FROM {TABLE} WHERE EXISTS (SELECT 1 FROM {TABLE} ORDER BY I)",
            ),
            ("LISTAGG DISTINCT, separator", f"SELECT LISTAGG(DISTINCT S, ',') FROM {TABLE}"),
            (
                "LISTAGG DISTINCT, separator, ordered",
                f"SELECT LISTAGG(DISTINCT S, ',') WITHIN GROUP (ORDER BY S) FROM {TABLE}",
            ),
            (
                "LISTAGG DISTINCT, ordered by another column",
                f"SELECT LISTAGG(DISTINCT S, ',') WITHIN GROUP (ORDER BY I) FROM {TABLE}",
            ),
            ("the REAL column, as the driver sees it", f"SELECT R FROM {TABLE}"),
            (
                "REAL in the catalog",
                "SELECT DATA_TYPE, LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE FROM "
                "QSYS2.SYSCOLUMNS "
                "WHERE TABLE_SCHEMA = 'QTEMP' AND TABLE_NAME = 'P6FLAG' AND COLUMN_NAME = 'R'",
            ),
        ):
            case(conn, results, key, sql)
    _execute(conn, f"DROP TABLE {TABLE}")
    if _execute(conn, f"CREATE TABLE {TABLE} (D DECFLOAT(34))")["result"] == "ok":
        for key, value, marker in DECFLOATS:
            _execute(conn, f"DELETE FROM {TABLE}")
            _step(
                results,
                f"bind {key}",
                _execute(conn, f"INSERT INTO {TABLE} VALUES ({marker})", [value]),
            )
            case(
                conn, results, f"read back {key}", f"SELECT D, CAST(D AS VARCHAR(50)) FROM {TABLE}"
            )
        case(
            conn,
            results,
            "a DECFLOAT compared to a typed marker",
            f"SELECT 1 FROM {TABLE} WHERE D = CAST(CAST(? AS VARCHAR(50)) AS DECFLOAT(34))",
            ("1",),
        )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
