"""Write probe 06: which column DEFAULT forms does CREATE TABLE accept?

Only declares temporary tables (DECLARE GLOBAL TEMPORARY TABLE SESSION.x, in QTEMP),
which disappear when the connection closes; nothing in a library changes.
Not part of probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_defaults

Question: Django's db_default compiles Value(1) to CAST(%s AS INTEGER), so
the backend wrote DEFAULT CAST(1 AS INTEGER), which failed with SQL0574 in
Django's basic tests. Which forms (plain constants, CAST, negative numbers,
strings, booleans, special registers) does a column DEFAULT accept, and what
does an INSERT then store? Includes strings with quotes and non-ASCII
characters as '...', N'...' and UX'...' constants per string column type.
Findings: docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import sys
from typing import Any

from _common import ProbeError, Settings, connect, run_statement, run_values, write_result

# (label, column definition)
CASES = [
    ("integer constant", "INTEGER DEFAULT 1"),
    ("negative integer", "INTEGER DEFAULT -1"),
    ("parenthesized integer", "INTEGER DEFAULT (1)"),
    ("cast integer", "INTEGER DEFAULT CAST(1 AS INTEGER)"),
    ("cast negative integer", "INTEGER DEFAULT CAST(-1 AS INTEGER)"),
    ("bigint constant", "BIGINT DEFAULT 9223372036854775807"),
    ("decimal constant", "DECIMAL(5, 2) DEFAULT 1.50"),
    ("cast decimal", "DECIMAL(5, 2) DEFAULT CAST(1.50 AS DECIMAL(5, 2))"),
    ("double constant", "DOUBLE DEFAULT 1.5E0"),
    ("string constant", "NVARCHAR(10) DEFAULT 'abc'"),
    ("cast string", "NVARCHAR(10) DEFAULT CAST('abc' AS NVARCHAR(10))"),
    ("empty string", "NVARCHAR(10) DEFAULT ''"),
    ("string with quote (NVARCHAR)", "NVARCHAR(10) DEFAULT 'O''Brien'"),
    ("string with quote (VARCHAR)", "VARCHAR(10) DEFAULT 'O''Brien'"),
    ("string with quote (CHAR)", "CHAR(10) DEFAULT 'O''Brien'"),
    ("string with percent", "NVARCHAR(10) DEFAULT '100%'"),
    ("N string with quote (NVARCHAR)", "NVARCHAR(10) DEFAULT N'O''Brien'"),
    ("N string with quote (VARCHAR)", "VARCHAR(10) DEFAULT N'O''Brien'"),
    ("N string with quote (CHAR)", "CHAR(10) DEFAULT N'O''Brien'"),
    ("N string with quote (NCLOB)", "NCLOB(1M) DEFAULT N'O''Brien'"),
    ("string with quote (NCLOB)", "NCLOB(1M) DEFAULT 'O''Brien'"),
    ("N string, two quotes", "NVARCHAR(20) DEFAULT N'''a''b'''"),
    ("N string, quote at end", "NVARCHAR(10) DEFAULT N'ab'''"),
    ("N string empty", "NVARCHAR(10) DEFAULT N''"),
    ("N string non-ASCII", "NVARCHAR(10) DEFAULT N'héllo \U0001f600'"),
    ("N string percent", "NVARCHAR(10) DEFAULT N'100%'"),
    ("N string hex (CHAR 32)", "CHAR(32) DEFAULT N'12345678123456781234567812345678'"),
    ("N string (VARCHAR 39)", "VARCHAR(39) DEFAULT N'::1'"),
    ("string non-ASCII (NVARCHAR)", "NVARCHAR(10) DEFAULT 'héllo \U0001f600'"),
    ("string BMP non-ASCII (NVARCHAR)", "NVARCHAR(10) DEFAULT 'héllo €'"),
    ("N string BMP non-ASCII (NVARCHAR)", "NVARCHAR(10) DEFAULT N'héllo €'"),
    ("string BMP non-ASCII (VARCHAR)", "VARCHAR(10) DEFAULT 'héllo'"),
    ("string emoji only (NVARCHAR)", "NVARCHAR(10) DEFAULT '\U0001f600'"),
    ("UX constant emoji (NVARCHAR)", "NVARCHAR(10) DEFAULT UX'D83DDE00'"),
    ("string with quote, no N (NVARCHAR 20)", "NVARCHAR(20) DEFAULT 'O''Brien'"),
    # UX'...': UTF-16 hex graphic constant ("O'Brien €" and "é😀").
    ("UX quote+euro (NVARCHAR)", "NVARCHAR(20) DEFAULT UX'004F00270042007200690065006E002020AC'"),
    ("UX quote (VARCHAR)", "VARCHAR(20) DEFAULT UX'004F00270042007200690065006E'"),
    ("UX e-acute+emoji (VARCHAR)", "VARCHAR(20) DEFAULT UX'00E9D83DDE00'"),
    ("UX quote (CHAR)", "CHAR(20) DEFAULT UX'004F00270042007200690065006E'"),
    ("UX quote (NCLOB)", "NCLOB(1M) DEFAULT UX'004F00270042007200690065006E'"),
    ("UX quote (NCHAR)", "NCHAR(10) DEFAULT UX'004F00270042007200690065006E'"),
    ("UX empty (NVARCHAR)", "NVARCHAR(10) DEFAULT UX''"),
    ("plain hex (CHAR 32)", "CHAR(32) DEFAULT '12345678123456781234567812345678'"),
    ("plain (NCHAR)", "NCHAR(10) DEFAULT 'abc'"),
    ("boolean TRUE", "BOOLEAN DEFAULT TRUE"),
    ("cast boolean", "BOOLEAN DEFAULT CAST(TRUE AS BOOLEAN)"),
    ("date literal", "DATE DEFAULT '2026-01-02'"),
    ("cast date", "DATE DEFAULT CAST('2026-01-02' AS DATE)"),
    ("timestamp special register", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ("expression 1 + 1", "INTEGER DEFAULT 1 + 1"),
    ("integer default on primary key", "INTEGER NOT NULL DEFAULT 1 PRIMARY KEY"),
]


def run(conn) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    accepted: dict[str, bool] = {}
    for index, (label, column) in enumerate(CASES):
        table = f"SESSION.DJDEF{index:02d}"
        created = run_statement(
            conn,
            label,
            f"DECLARE GLOBAL TEMPORARY TABLE {table} (K INTEGER, C {column}) "
            "ON COMMIT PRESERVE ROWS WITH REPLACE",
        )
        steps.append(created)
        accepted[label] = created["ok"]
        if created["ok"]:
            steps.append(
                run_statement(conn, f"{label}: insert", f"INSERT INTO {table} (K) VALUES (1)")
            )
            steps.append(run_values(conn, f"{label}: stored", f"SELECT C FROM {table}"))
    print("\nSummary")
    for label, ok in accepted.items():
        print(f"  {label:<40} {'accepted' if ok else 'REJECTED'}")
    return {"steps": steps, "accepted": accepted}


def main(argv: list[str]) -> int:
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        conn = connect(settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1"}, autocommit=True)
        result = run(conn)
        print(f"\nresult saved to {write_result('w06_defaults', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
