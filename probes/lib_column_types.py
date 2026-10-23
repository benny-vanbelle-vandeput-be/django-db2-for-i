"""Write probe 14: how the catalog records each column type the backend writes (phase 4, step B).

THIS CHANGES THE IBM i: four tables with the prefix DJW14 in the journaled
default library, all dropped at the end (also after a failure). Approved by
the maintainer on 2026-10-23 (step B item 6) under these conditions: own
prefixed tables, each recorded on the table list (tests/table_registry.py)
before its CREATE TABLE so bin/ibmi-cleanup covers it, always cleaned up,
nothing else read or changed, one connection, nothing else on PUB400 at the
same time (scripts/pub400.sh holds the PUB400 lock for the whole run). Not
part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_column_types              # dry run: checks only
    bin/probe --approved <link> lib_column_types -- --execute

Questions (data_types_reverse, get_field_type(), get_table_description(),
can_introspect_default, can_introspect_check_constraints):
1. QSYS2.SYSCOLUMNS for every column type of DatabaseWrapper.data_types:
   DATA_TYPE, LENGTH, precision, scale, CCSID, the identity columns;
2. the same for the three identity types (one identity column per table,
   hence DJW14A / DJW14B / DJW14S);
3. COLUMN_DEFAULT for typical db_default values (numbers, text with a
   quote, boolean, timestamps, NULL);
4. a column CHECK in Django's form: SYSCST, SYSCHKCST.CHECK_CLAUSE, SYSCSTCOL;
5. what the driver reports in cursor.description for each column.

QTEMP tables are not in the catalog (probe 25), hence the default library.
Every catalog query is limited to the probe's own tables.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path
from typing import Any

from _common import (
    ProbeError,
    Settings,
    connect,
    print_query,
    run_query,
    run_statement,
    write_result,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from django_db2_for_i.base import DatabaseWrapper
from tests import table_registry

TYPES, AUTO, BIGAUTO, SMALLAUTO = "DJW14T", "DJW14A", "DJW14B", "DJW14S"
OWN_TABLES = (TYPES, AUTO, BIGAUTO, SMALLAUTO)
IDENTITY = {AUTO: "AutoField", BIGAUTO: "BigAutoField", SMALLAUTO: "SmallAutoField"}
PROBE_OBJECTS = (
    "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X WHERE OBJNAME LIKE 'DJW14%'"
)
# Values for the data_types templates.
PARAMS = {"max_length": 20, "max_digits": 7, "decimal_places": 2}
# db_default values as Django's schema editor writes them (column, type, DEFAULT clause).
DEFAULTS = (
    ("D_INT", "INTEGER", "42"),
    ("D_NEG", "INTEGER", "-1"),
    ("D_DEC", "DECIMAL(5, 2)", "1.50"),
    ("D_DOUBLE", "DOUBLE", "2.5"),
    ("D_TEXT", "NVARCHAR(10)", "'abc'"),
    ("D_QUOTE", "NVARCHAR(10)", "'it''s'"),
    ("D_EMPTY", "NVARCHAR(10)", "''"),
    ("D_BOOL", "BOOLEAN", "TRUE"),
    ("D_DATE", "DATE", "CURRENT DATE"),
    ("D_TS", "TIMESTAMP(6)", "CURRENT TIMESTAMP"),
    ("D_NULL", "INTEGER", "NULL"),
)
COLUMNS = (
    "SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE, LENGTH, "
    "NUMERIC_PRECISION, NUMERIC_SCALE, NUMERIC_PRECISION_RADIX, "
    "CHARACTER_MAXIMUM_LENGTH, CHARACTER_OCTET_LENGTH, CCSID, IS_NULLABLE, "
    "HAS_DEFAULT, COLUMN_DEFAULT, IS_IDENTITY, IDENTITY_GENERATION "
    "FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN ({names}) "
    "ORDER BY TABLE_NAME, ORDINAL_POSITION"
)


def type_columns() -> list[tuple[str, str, str]]:
    """(column, Django field, column type) for every non-identity data_types entry."""
    columns = []
    for field, template in DatabaseWrapper.data_types.items():
        if "IDENTITY" in template:
            continue
        columns.append((f"F_{field.upper()}", field, template % PARAMS))
    return columns


def checks(conn, library: str) -> None:
    schema = run_query(conn, "CURRENT SCHEMA", "SELECT CURRENT SCHEMA AS S FROM SYSIBM.SYSDUMMY1")
    print_query(schema)
    if not schema["ok"] or [row.get("S") for row in schema["rows"]] != [library]:
        raise ProbeError("check", "CURRENT SCHEMA is not the default library; nothing was changed")
    journal = run_query(
        conn,
        f"{library}: QSQJRN journal",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) X",
        (library,),
    )
    existing = run_query(
        conn, f"{library}: probe tables that exist already", PROBE_OBJECTS, (library,)
    )
    for result in (journal, existing):
        print_query(result)
    if not journal["ok"] or not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; nothing was changed")
    if existing["rows"]:
        raise ProbeError("check", f"DJW14 tables exist in {library}; nothing was changed")
    if table_registry.list_path() is None:
        raise ProbeError(
            "check",
            f"{table_registry.ENV} is not set (run through scripts/pub400.sh); nothing was changed",
        )
    print("\ncolumn types:")
    for column, field, sql_type in type_columns():
        print(f"  {column:<32} {field:<26} {sql_type}")


def _own(conn, label: str, sql: str, library: str) -> dict[str, Any]:
    """A catalog query limited to the probe's own tables (TABLE_SCHEMA, TABLE_NAME IN ...)."""
    marks = ", ".join("?" for _ in OWN_TABLES)
    result = run_query(conn, label, sql.format(names=marks), (library, *OWN_TABLES))
    print_query(result)
    return result


def describe(conn, table: str) -> list[list[Any]]:
    """cursor.description of an empty SELECT * (name, type code, sizes, null_ok)."""
    cursor = conn.cursor()
    try:
        cursor.execute(f"SELECT * FROM {table} FETCH FIRST 0 ROWS ONLY")
        rows = [
            [
                name,
                getattr(type_code, "__name__", str(type_code)),
                display,
                internal,
                prec,
                scale,
                null,
            ]
            for name, type_code, display, internal, prec, scale, null in cursor.description
        ]
    finally:
        cursor.close()
    for row in rows:
        print(f"    {row}")
    return rows


def run(conn, library: str) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    catalog: dict[str, Any] = {}
    created: list[str] = []
    registry = table_registry.list_path()

    def create(name: str, body: str) -> None:
        sql = f"CREATE TABLE {library}.{name} ({body})"
        entry = table_registry.parse(sql, library)
        assert entry is not None and entry.name == name
        table_registry.record(registry, entry)
        result = run_statement(conn, f"create {name}", sql)
        steps.append(result)
        if not result["ok"]:
            raise ProbeError("refused", f"create {name} failed: {result['message'][:200]}")
        created.append(name)

    try:
        print("\n======== setup ========")
        columns = [f"{column} {sql_type}" for column, _field, sql_type in type_columns()]
        columns += [f"{column} {sql_type} DEFAULT {value}" for column, sql_type, value in DEFAULTS]
        # A column check as Django writes it (data_type_check_constraints).
        columns.append("K_POS INTEGER NOT NULL CHECK (k_pos >= 0)")
        create(TYPES, ", ".join(columns))
        for name, field in IDENTITY.items():
            create(name, f"ID {DatabaseWrapper.data_types[field]} NOT NULL PRIMARY KEY")

        print("\n======== 1-3. SYSCOLUMNS ========")
        catalog["columns"] = _own(conn, "SYSCOLUMNS of the probe tables", COLUMNS, library)
        print("\n======== 4. column check ========")
        catalog["check"] = _own(
            conn,
            "SYSCST, SYSCHKCST and SYSCSTCOL of the check",
            "SELECT C.CONSTRAINT_NAME, C.CONSTRAINT_TYPE, K.CHECK_CLAUSE, S.COLUMN_NAME "
            "FROM QSYS2.SYSCST C "
            "JOIN QSYS2.SYSCHKCST K ON K.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA "
            "AND K.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
            "LEFT JOIN QSYS2.SYSCSTCOL S ON S.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA "
            "AND S.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
            "WHERE C.TABLE_SCHEMA = ? AND C.TABLE_NAME IN ({names})",
            library,
        )
        print("\n======== 5. cursor.description ========")
        catalog["description"] = {}
        for name in created:
            print(f"  {name}:")
            catalog["description"][name] = describe(conn, f"{library}.{name}")
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        for name in reversed(created):
            steps.append(run_statement(conn, f"drop {name}", f"DROP TABLE {library}.{name}"))
        left = run_query(conn, "probe tables left", PROBE_OBJECTS, (library,))
        print_query(left)
        if not left["ok"] or left["rows"]:
            print(f"\nWARNING: DJW14 objects may be left in {library}: {left}", file=sys.stderr)
    print("\nSummary")
    for result in steps:
        state = "ok" if result["ok"] else f"{result.get('sqlstate', '')} {result['message'][:100]}"
        print(f"  {result['label'][:60]:<60} {state}")
    return {"steps": steps, "catalog": catalog, "left": left.get("rows")}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, read and drop the tables")
    args = parser.parse_args(argv)
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        # DBQ as the backend sets it: the library becomes CURRENT SCHEMA, so the
        # system-named check constraint lands next to its table.
        conn = connect(
            settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1", "DBQ": library}, autocommit=True
        )
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('lib_column_types', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
