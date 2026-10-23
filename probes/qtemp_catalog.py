"""Probe 25: the catalog views introspection needs (phase 4, step A).

Read-only outside QTEMP. It reads:

- the columns of QSYS2.SYSINDEXES, SYSKEYS, SYSCST, SYSKEYCST, SYSCHKCST,
  SYSREFCST, SYSCOLUMNS and SYSCSTCOL from the views' own SYSCOLUMNS rows
  (name, type, length, scale, nullable, and the column text Db2 for i gives,
  which describes the coded values), so get_constraints(),
  get_relations() and can_introspect_default are built from what is there;
- the values of the coded columns (constraint types, rules, index ordering,
  uniqueness, default and identity columns) as they occur in the two .env
  libraries (counts only, never table contents);
- whether objects in QTEMP appear in these views: it creates one QTEMP table
  with an index and a primary-key-like unique index (QTEMP takes no
  constraints, SQL7008), and looks for them.

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

VIEWS = (
    "SYSINDEXES",
    "SYSKEYS",
    "SYSCST",
    "SYSKEYCST",
    "SYSCHKCST",
    "SYSREFCST",
    "SYSCOLUMNS",
    # The columns a CHECK constraint references (step B item 4), if the view exists.
    "SYSCSTCOL",
)
# Coded columns whose values introspection maps: (view, column, library column).
CODED = (
    ("SYSCST", "CONSTRAINT_TYPE", "TABLE_SCHEMA"),
    ("SYSCST", "IS_DEFERRABLE", "TABLE_SCHEMA"),
    ("SYSCST", "INITIALLY_DEFERRED", "TABLE_SCHEMA"),
    ("SYSREFCST", "UPDATE_RULE", "CONSTRAINT_SCHEMA"),
    ("SYSREFCST", "DELETE_RULE", "CONSTRAINT_SCHEMA"),
    ("SYSREFCST", "MATCH_OPTION", "CONSTRAINT_SCHEMA"),
    ("SYSINDEXES", "IS_UNIQUE", "TABLE_SCHEMA"),
    ("SYSKEYS", "ORDERING", "INDEX_SCHEMA"),
    ("SYSCOLUMNS", "HAS_DEFAULT", "TABLE_SCHEMA"),
    ("SYSCOLUMNS", "IS_IDENTITY", "TABLE_SCHEMA"),
    ("SYSCOLUMNS", "IS_NULLABLE", "TABLE_SCHEMA"),
    ("SYSCOLUMNS", "DATA_TYPE", "TABLE_SCHEMA"),
)


def _rows(conn, sql: str, params=()) -> list:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        return [list(row) for row in cursor.fetchall()]
    except pyodbc.Error as exc:
        return [["error", str(exc.args[0]) if exc.args else "", str(exc)[:160]]]
    finally:
        cursor.close()


def _execute(conn, sql: str) -> str:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return "ok"
    except pyodbc.Error as exc:
        return f"error {exc.args[0] if exc.args else ''}"
    finally:
        cursor.close()


def view_columns(conn) -> dict[str, list]:
    return {
        view: _rows(
            conn,
            "SELECT COLUMN_NAME, DATA_TYPE, LENGTH, NUMERIC_SCALE, IS_NULLABLE, COLUMN_TEXT "
            "FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = 'QSYS2' AND TABLE_NAME = ? "
            "ORDER BY ORDINAL_POSITION",
            (view,),
        )
        for view in VIEWS
    }


def coded_values(conn, libraries: list[str]) -> dict[str, list]:
    marks = ", ".join("?" for _ in libraries)
    return {
        f"{view}.{column}": _rows(
            conn,
            f"SELECT {column}, COUNT(*) FROM QSYS2.{view} WHERE {library} IN ({marks}) "
            f"GROUP BY {column} ORDER BY {column}",
            tuple(libraries),
        )
        for view, column, library in CODED
    }


def qtemp_visibility(conn) -> dict[str, Any]:
    setup = [
        _execute(conn, "DROP TABLE QTEMP.P25T"),
        _execute(conn, "CREATE TABLE QTEMP.P25T (ID INTEGER NOT NULL, A INTEGER DEFAULT 3)"),
        _execute(conn, "CREATE UNIQUE INDEX QTEMP.P25U ON QTEMP.P25T (ID)"),
        _execute(conn, "CREATE INDEX QTEMP.P25I ON QTEMP.P25T (A DESC)"),
    ]
    try:
        return {
            "setup": setup[1:],
            "SYSTABLES": _rows(
                conn, "SELECT TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = 'QTEMP'"
            ),
            "SYSCOLUMNS": _rows(
                conn,
                "SELECT COLUMN_NAME, ORDINAL_POSITION, HAS_DEFAULT, COLUMN_DEFAULT "
                "FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = 'QTEMP' ORDER BY ORDINAL_POSITION",
            ),
            "SYSINDEXES": _rows(
                conn,
                "SELECT INDEX_NAME, IS_UNIQUE FROM QSYS2.SYSINDEXES WHERE INDEX_SCHEMA = 'QTEMP'",
            ),
            "SYSKEYS": _rows(
                conn,
                "SELECT INDEX_NAME, COLUMN_NAME, ORDINAL_POSITION, ORDERING "
                "FROM QSYS2.SYSKEYS WHERE INDEX_SCHEMA = 'QTEMP'",
            ),
        }
    finally:
        _execute(conn, "DROP TABLE QTEMP.P25T")


def run(settings: Settings, conn) -> dict[str, Any]:
    libraries = [lib for lib in (settings.default_library, settings.other_library) if lib]
    results: dict[str, Any] = {"view columns": view_columns(conn)}
    for view, columns in results["view columns"].items():
        print(f"\n  QSYS2.{view}: {len(columns)} columns")
        for column in columns:
            print(f"    {column}")
    if libraries:
        results["coded values"] = coded_values(conn, libraries)
        print("\n  coded values in the two .env libraries (value, count):")
        for name, values in results["coded values"].items():
            print(f"    {name:<28} {values}")
    results["QTEMP in the catalog"] = qtemp_visibility(conn)
    print(f"\n  QTEMP in the catalog: {results['QTEMP in the catalog']}")
    return results
