"""A review of the flags that are off: the ones a probe has not answered yet.

Writes only to QTEMP (tables gone with the job); reads nothing outside it but
SYSIBM.SYSDUMMY1. Without commitment control. One connection, no retries. Each
statement's rows, or its SQLSTATE and SQLCODE, are recorded.

- ``supports_date_lookup_using_string``: Django's test filters a ``DateTimeField``
  with ``__startswith="2005"``, as PostgreSQL does with ``column::text``. Which text
  forms of a ``TIMESTAMP``, ``DATE`` and ``TIME`` Db2 for i gives (``CHAR``,
  ``CAST AS VARCHAR``, ``VARCHAR_FORMAT``), and whether ``LIKE`` takes them with a
  parameter pattern. A second round looks at the timestamp forms, which matched
  nothing with a plain ``?`` pattern: a literal pattern, a cast parameter, a cast
  value, ``=`` and the bytes of the value.
- ``supports_expression_defaults`` and ``supports_uuid4_function_in_default``: a
  column ``DEFAULT`` that is an expression (``1 + 1``, ``UPPER('x')``,
  ``CURRENT_TIMESTAMP + 1 DAY``), ``GENERATE_UUID()`` and the form ``UUID4()`` takes
  (``LOWER(REPLACE(GENERATE_UUID(), '-', ''))``); ``CURRENT_TIMESTAMP`` alone is the
  control.

Usage (inside the "tests" container):
    nox -s probe -- flag_review

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute, _rows
from qtemp_later_flags import _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PFRD"

TEXT_FORMS = (
    ("timestamp: CHAR", "CHAR(T)"),
    ("timestamp: CAST AS VARCHAR(32)", "CAST(T AS VARCHAR(32))"),
    ("timestamp: VARCHAR_FORMAT ISO", "VARCHAR_FORMAT(T, 'YYYY-MM-DD HH24:MI:SS.FF6')"),
    ("date: CHAR", "CHAR(D)"),
    ("date: CHAR ISO", "CHAR(D, ISO)"),
    ("date: CAST AS VARCHAR(10)", "CAST(D AS VARCHAR(10))"),
    ("date: VARCHAR_FORMAT", "VARCHAR_FORMAT(D, 'YYYY-MM-DD')"),
    ("time: CHAR", "CHAR(TM)"),
    ("time: CHAR JIS", "CHAR(TM, JIS)"),
    ("time: CAST AS VARCHAR(8)", "CAST(TM AS VARCHAR(8))"),
    ("time: VARCHAR_FORMAT", "VARCHAR_FORMAT(TM, 'HH24:MI:SS')"),
)

LIKE_FORMS = (
    ("like: timestamp, VARCHAR_FORMAT", "VARCHAR_FORMAT(T, 'YYYY-MM-DD HH24:MI:SS.FF6')"),
    ("like: timestamp, CAST AS VARCHAR", "CAST(T AS VARCHAR(32))"),
    ("like: date, VARCHAR_FORMAT", "VARCHAR_FORMAT(D, 'YYYY-MM-DD')"),
    ("like: date, CHAR ISO", "CHAR(D, ISO)"),
    ("like: time, CHAR JIS", "CHAR(TM, JIS)"),
)

DEFAULTS = (
    ("default: CURRENT_TIMESTAMP (control)", "TIMESTAMP", "CURRENT_TIMESTAMP"),
    ("default: CURRENT_TIMESTAMP + 1 DAY", "TIMESTAMP", "CURRENT_TIMESTAMP + 1 DAY"),
    ("default: 1 + 1", "INTEGER", "1 + 1"),
    ("default: (1 + 1)", "INTEGER", "(1 + 1)"),
    ("default: UPPER('x')", "VARCHAR(10)", "UPPER('x')"),
    ("default: GENERATE_UUID()", "VARCHAR(36)", "GENERATE_UUID()"),
    (
        "default: LOWER(REPLACE(GENERATE_UUID(), '-', ''))",
        "CHAR(32)",
        "LOWER(REPLACE(GENERATE_UUID(), '-', ''))",
    ),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (PFRD* tables, gone with the job)"}

    # 1. Text forms of date and time values, and LIKE on them.
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _step(
        results,
        "create table",
        _execute(conn, f"CREATE TABLE {TABLE} (T TIMESTAMP, D DATE, TM TIME)"),
    )
    if created["result"] == "ok":
        _step(
            results,
            "insert",
            _execute(
                conn,
                f"INSERT INTO {TABLE} VALUES "
                "(TIMESTAMP '2005-07-28 12:30:05.123456', DATE '2005-07-28', TIME '12:30:05'), "
                "(TIMESTAMP '2006-01-02 00:00:00', DATE '2006-01-02', TIME '00:00:00')",
            ),
        )
        for key, expression in TEXT_FORMS:
            rows = _rows(conn, f"SELECT {expression} FROM {TABLE} ORDER BY T")
            _step(results, key, {"rows": rows})
        for key, expression in LIKE_FORMS:
            _step(
                results,
                key,
                {
                    "rows": _rows(
                        conn,
                        f"SELECT COUNT(*) FROM {TABLE} WHERE {expression} LIKE ? ESCAPE '\\'",
                        ("2005%" if not key.startswith("like: time") else "12:30%",),
                    )
                },
            )
        # Round 2: the timestamp forms matched nothing with a parameter pattern.
        iso = "VARCHAR_FORMAT(T, 'YYYY-MM-DD HH24:MI:SS.FF6')"
        for key, sql, params in (
            ("ts2: literal pattern", f"SELECT COUNT(*) FROM {TABLE} WHERE {iso} LIKE '2005%'", ()),
            (
                "ts2: parameter cast to VARCHAR(40)",
                f"SELECT COUNT(*) FROM {TABLE} WHERE {iso} LIKE CAST(? AS VARCHAR(40))",
                ("2005%",),
            ),
            (
                "ts2: parameter cast to NVARCHAR(40)",
                f"SELECT COUNT(*) FROM {TABLE} WHERE {iso} LIKE CAST(? AS NVARCHAR(40))",
                ("2005%",),
            ),
            (
                "ts2: value cast to NVARCHAR(32)",
                f"SELECT COUNT(*) FROM {TABLE} WHERE CAST({iso} AS NVARCHAR(32)) LIKE ?",
                ("2005%",),
            ),
            (
                "ts2: CHAR(T) cast to NVARCHAR(32)",
                f"SELECT COUNT(*) FROM {TABLE} WHERE CAST(CHAR(T) AS NVARCHAR(32)) LIKE ?",
                ("2005%",),
            ),
            (
                "ts2: = with a parameter",
                f"SELECT COUNT(*) FROM {TABLE} WHERE {iso} = ?",
                ("2005-07-28 12:30:05.123456",),
            ),
            (
                "ts2: length, HEX of the first 4 characters",
                f"SELECT LENGTH({iso}), HEX(LEFT({iso}, 4)), HEX(LEFT(CHAR(D, ISO), 4)) "
                f"FROM {TABLE} ORDER BY T",
                (),
            ),
        ):
            _step(results, key, {"rows": _rows(conn, sql, params)})
        _step(
            results,
            "like: timestamp column itself (expected SQL0414)",
            _execute(conn, f"SELECT COUNT(*) FROM {TABLE} WHERE T LIKE ?", ("2005%",)),
        )
    _execute(conn, f"DROP TABLE {TABLE}")

    # 2. Column defaults that are expressions.
    for number, (key, column_type, default) in enumerate(DEFAULTS, start=1):
        table = f"{TABLE}{number}"
        _execute(conn, f"DROP TABLE {table}")
        outcome = _step(
            results,
            key,
            _execute(conn, f"CREATE TABLE {table} (ID INTEGER, V {column_type} DEFAULT {default})"),
        )
        if outcome["result"] == "ok":
            _execute(conn, f"INSERT INTO {table} (ID) VALUES (1)")
            _execute(conn, f"INSERT INTO {table} (ID) VALUES (2)")
            outcome["rows"] = _rows(conn, f"SELECT ID, V FROM {table} ORDER BY ID")
        _execute(conn, f"DROP TABLE {table}")
    return results
