"""Are the full-width percent and low line LIKE wildcards? (audit F-15, remediation P-4)

The backend escapes ``%``, ``_`` and ``\\`` in LIKE patterns (``contains``,
``startswith``, ...). The audit (F-15) suspects that in a graphic or
Unicode pattern the full-width percent (U+FF05) and low line (U+FF3F) are
wildcards as well; those are not escaped today. This probe records, on an ``NVARCHAR``
column (``CharField``) with the values a, U+FF05, b / a, U+FF3F, b / ``axb``
and ``axyb``:

- ``LIKE ? ESCAPE '\\'`` with those two values as patterns (unescaped);
- the same with a backslash before the full-width character (escaped with the
  backend's escape character);
- the backend's ``contains`` form for a column pattern (``LIKE '%' || ? || '%'``)
  with U+FF05 alone.

Writes only to QTEMP (one table, gone with the job), without commitment
control (CMT=0). One connection, one statement per step, no retries.

Usage (inside the "tests" container):
    nox -s probe -- like_fullwidth

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute
from qtemp_later_flags import _query, _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PLIKEFW"
PERCENT = chr(0xFF05)  # FULLWIDTH PERCENT SIGN
LOW_LINE = chr(0xFF3F)  # FULLWIDTH LOW LINE
VALUES = ("a" + PERCENT + "b", "a" + LOW_LINE + "b", "axb", "axyb")

PATTERNS = (
    ("full-width percent, unescaped", "a" + PERCENT + "b"),
    ("full-width low line, unescaped", "a" + LOW_LINE + "b"),
    ("full-width percent, escaped", "a\\" + PERCENT + "b"),
    ("full-width low line, escaped", "a\\" + LOW_LINE + "b"),
    ("ASCII percent (control)", "a%b"),
    ("ASCII percent, escaped (control)", "a\\%b"),
)


def connection_attributes(settings: Settings) -> dict[str, str]:
    """The backend's attributes without commitment control (QTEMP has no journal)."""
    import pyodbc

    pyodbc.pooling = False
    return {**BACKEND, "CMT": "0"}


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (one table), CMT=0"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(
        results,
        "create",
        _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER NOT NULL, S NVARCHAR(10))"),
    )
    if created["result"] != "ok":
        return results
    for number, value in enumerate(VALUES, 1):
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?)", (number, value))
    _step(results, "stored", _query(conn, f"SELECT ID, S, HEX(S) FROM {TABLE} ORDER BY ID"))
    for label, pattern in PATTERNS:
        _step(
            results,
            f"LIKE ? ESCAPE, {label}",
            _query(
                conn,
                f"SELECT ID FROM {TABLE} WHERE S LIKE ? ESCAPE '\\' ORDER BY ID",
                (pattern,),
            ),
        )
    _step(
        results,
        "contains form, full-width percent",
        _query(
            conn,
            f"SELECT ID FROM {TABLE} WHERE S LIKE '%' || ? || '%' ESCAPE '\\' ORDER BY ID",
            (PERCENT,),
        ),
    )
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
