"""A Decimal value with more digits than its DecimalField (#95).

``Value(Decimal("123456.789"), output_field=DecimalField(max_digits=5,
decimal_places=2))`` is written ``CAST(? AS DECIMAL(5, 2))``. This shows what
the driver and Db2 for i do with such a marker, and with the alternatives: the
value's own ``DECIMAL(p, s)`` (as #78 does for strings), and a marker without a
cast.

Read-only: SELECTs from SYSIBM.SYSDUMMY1, nothing is created. One connection,
no retries. Each statement's rows, or its SQLSTATE and SQLCODE, are recorded.

Usage (inside the "tests" container):
    nox -s probe -- decimal_values

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _common import Settings
from qtemp_later_flags import connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

DUMMY = "FROM SYSIBM.SYSDUMMY1"

# key, the marker's SQL, the value
CASES: tuple[tuple[str, str, Any], ...] = (
    ("fits DECIMAL(5, 2)", "CAST(? AS DECIMAL(5, 2))", Decimal("123.45")),
    ("more integer digits than DECIMAL(5, 2)", "CAST(? AS DECIMAL(5, 2))", Decimal("123456.78")),
    ("more decimals than DECIMAL(5, 2)", "CAST(? AS DECIMAL(5, 2))", Decimal("1.2345")),
    ("both, DECIMAL(5, 2)", "CAST(? AS DECIMAL(5, 2))", Decimal("123456.789")),
    ("its own DECIMAL(9, 3)", "CAST(? AS DECIMAL(9, 3))", Decimal("123456.789")),
    (
        "its own, then cast to DECIMAL(5, 2)",
        "CAST(CAST(? AS DECIMAL(9, 3)) AS DECIMAL(5, 2))",
        Decimal("123456.789"),
    ),
    ("an untyped marker", "?", Decimal("123456.789")),
    ("an untyped marker, + 0", "? + 0", Decimal("123456.789")),
    ("63 digits, its own DECIMAL(63, 3)", "CAST(? AS DECIMAL(63, 3))", Decimal("1" * 60 + ".123")),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "read-only (SYSIBM.SYSDUMMY1)"}
    for key, marker, value in CASES:
        case(conn, results, key, f"SELECT {marker} {DUMMY}", (value,))
    return results
