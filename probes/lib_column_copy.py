"""Renaming a column by copying it, with constraints (#258 F).

QTEMP takes no constraints (a constraint needs a journal), so ``qtemp_column_copy``
could not try them. This probe does, as the opt-in column rename would in a migration.

THIS CHANGES THE IBM i, in the default library (DB2I_DEFAULT_LIBRARY, the journaled
test library) only: tables DJDB2I_CCP (ID INTEGER NOT NULL PRIMARY KEY, CODE
VARCHAR(10) NOT NULL UNIQUE, N INTEGER CHECK (N >= 0)) and DJDB2I_CCC (ID INTEGER NOT
NULL PRIMARY KEY, P_CODE VARCHAR(10) REFERENCES DJDB2I_CCP (CODE)), each recorded on the
cleanup list (tests/table_registry.py) before its CREATE TABLE; 3 and 2 rows. Under
commitment control, with CPA32B2 suppressed for its own job (QTEMP copy of QAQQINI, as
the backend does):

a. ``DROP COLUMN ... RESTRICT`` while a constraint depends on the column (CODE: unique
   and referenced by the child's foreign key; N: a check), each rolled back;
0. when the first ``UPDATE ... WITH NC`` after DDL of the table works (a column X
   added, with and without other DDL before or after it; each rolled back);
b. the copy steps for CODE and N (drop the constraints, ADD COLUMN ... BEFORE, copy,
   NOT NULL, the constraints again from the catalog, the label, DROP COLUMN ...
   RESTRICT), ending in ROLLBACK: is everything as it was? The copy is an UPDATE ...
   WITH NC: under commitment control a changed row makes every later ALTER TABLE of
   the table SQL0910 (a first run of this probe), and the copied values are in the
   new column only, which the rollback removes. Both old columns are dropped last:
   after a DROP COLUMN, even an UPDATE ... WITH NC of the table is SQL0910 (the second
   run of this probe).
c. the same steps, ending in COMMIT: constraints, names, order and enforcement.

Reads SYSCST, SYSREFCST, SYSCHKCST, SYSKEYCST and SYSCOLUMNS for these two tables.

Approval: issue #258 (comment 6865729024). At the end, also after a failure: both
tables dropped (child first), and a check that no DJDB2I_CC* object is left.

Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_column_copy              # dry run: checks only
    bin/probe --approved <link> lib_column_copy -- --execute

One connection with the backend's attributes (CMT=1, TRUEAUTOCOMMIT=1), no retries.
"""

from __future__ import annotations

import argparse
import contextlib
import re
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
from django_db2_for_i import inquiry
from tests import table_registry

PARENT = "DJDB2I_CCP"
CHILD = "DJDB2I_CCC"
OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"
LEFT = (
    "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X "
    "WHERE OBJNAME LIKE 'DJDB2I_CC%' OR OBJLONGNAME LIKE 'DJDB2I_CC%'"
)
CONSTRAINTS = (
    "SELECT C.TABLE_NAME, C.CONSTRAINT_NAME, C.CONSTRAINT_TYPE, K.COLUMN_NAME "
    "FROM QSYS2.SYSCST C LEFT JOIN QSYS2.SYSKEYCST K "
    "ON K.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND K.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
    "WHERE C.TABLE_SCHEMA = ? AND C.TABLE_NAME IN (?, ?) "
    "ORDER BY C.TABLE_NAME, C.CONSTRAINT_TYPE, C.CONSTRAINT_NAME, K.ORDINAL_POSITION"
)
COLUMNS = (
    "SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, IS_NULLABLE, COLUMN_TEXT "
    "FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN (?, ?) "
    "ORDER BY TABLE_NAME, ORDINAL_POSITION"
)


def sqlcode(message: str) -> str:
    match = re.search(r"\((-?\d+)\)", message)
    return match.group(1) if match else "?"


class Probe:
    def __init__(self, conn, library: str):
        self.conn = conn
        self.library = library
        self.parent = f"{library}.{PARENT}"
        self.child = f"{library}.{CHILD}"
        self.registry = table_registry.list_path()
        self.steps: list[dict[str, Any]] = []

    def run(self, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
        result = run_statement(self.conn, label, sql, params)
        self.steps.append(result)
        if result["ok"]:
            return {"sql": sql, "result": "ok"}
        return {
            "sql": sql,
            "result": sqlcode(result.get("message", "")),
            "message": result.get("message", "")[:200],
        }

    def must(self, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
        outcome = self.run(label, sql, params)
        if outcome["result"] != "ok":
            raise ProbeError("step", f"{label} failed: {outcome.get('message')}")
        return outcome

    def rows(self, label: str, sql: str, params: tuple = ()) -> list[dict[str, Any]] | str:
        result = run_query(self.conn, label, sql, params)
        print_query(result)
        if not result["ok"]:
            return f"error {result.get('sqlstate')} {result.get('message', '')[:120]}"
        return result["rows"]

    def state(self, label: str) -> dict[str, Any]:
        names = (self.library, PARENT, CHILD)
        return {
            "constraints": self.rows(f"{label}: constraints", CONSTRAINTS, names),
            "columns": self.rows(f"{label}: columns", COLUMNS, names),
            "rows": self.rows(f"{label}: rows", f"SELECT * FROM {self.parent} ORDER BY ID"),
        }

    def exists(self, name: str) -> bool:
        result = run_query(self.conn, f"{name} exists", OBJECTS, (self.library, name))
        return bool(result["ok"] and result["rows"])

    def create(self, table: str, body: str) -> None:
        sql = f"CREATE TABLE {self.library}.{table} ({body})"
        entry = table_registry.parse(sql, self.library)
        assert entry is not None and (entry.library, entry.name) == (self.library, table)
        table_registry.record(self.registry, entry)
        self.must(f"create {table}", sql)

    def one(self, label: str, sql: str, params: tuple) -> dict[str, Any]:
        rows = self.rows(label, sql, params)
        if not isinstance(rows, list) or len(rows) != 1:
            raise ProbeError("catalog", f"{label}: expected one row, got {rows}")
        return rows[0]

    def copy(self, results: dict[str, Any], prefix: str) -> None:
        """The copy steps for CODE (unique, referenced) and N (check, label)."""
        library = self.library
        unique = self.one(
            f"{prefix}: unique on CODE",
            "SELECT C.CONSTRAINT_NAME FROM QSYS2.SYSCST C JOIN QSYS2.SYSKEYCST K "
            "ON K.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA AND K.CONSTRAINT_NAME = "
            "C.CONSTRAINT_NAME WHERE C.TABLE_SCHEMA = ? AND C.TABLE_NAME = ? "
            "AND C.CONSTRAINT_TYPE = 'UNIQUE' AND K.COLUMN_NAME = 'CODE'",
            (library, PARENT),
        )["CONSTRAINT_NAME"]
        reference = self.one(
            f"{prefix}: foreign key to CODE",
            "SELECT R.CONSTRAINT_NAME, R.UPDATE_RULE, R.DELETE_RULE FROM QSYS2.SYSREFCST R "
            "JOIN QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = R.CONSTRAINT_SCHEMA AND "
            "C.CONSTRAINT_NAME = R.CONSTRAINT_NAME WHERE C.TABLE_SCHEMA = ? AND "
            "C.TABLE_NAME = ? AND R.UNIQUE_CONSTRAINT_NAME = ?",
            (library, CHILD, unique),
        )
        check = self.one(
            f"{prefix}: check on N",
            "SELECT H.CONSTRAINT_NAME, H.CHECK_CLAUSE FROM QSYS2.SYSCHKCST H JOIN "
            "QSYS2.SYSCST C ON C.CONSTRAINT_SCHEMA = H.CONSTRAINT_SCHEMA AND "
            "C.CONSTRAINT_NAME = H.CONSTRAINT_NAME WHERE C.TABLE_SCHEMA = ? AND C.TABLE_NAME = ?",
            (library, PARENT),
        )
        label = self.one(
            f"{prefix}: label of N",
            "SELECT COLUMN_TEXT FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = ? AND "
            "TABLE_NAME = ? AND COLUMN_NAME = 'N'",
            (library, PARENT),
        )["COLUMN_TEXT"]
        clause = str(check["CHECK_CLAUSE"])
        new_clause = re.sub(r'\bN\b|"N"', '"NEW_N"', clause)
        results[f"{prefix}: catalog"] = {
            "unique": unique,
            "foreign key": reference,
            "check": check,
            "check rewritten": new_clause,
            "label": label,
        }
        fk = f'"{reference["CONSTRAINT_NAME"]}"'
        # All DDL that comes before the copies, the copies, then the rest: the
        # order the schema editor uses (the rest is deferred to its end).
        steps = [
            ("drop the foreign key", f"ALTER TABLE {self.child} DROP CONSTRAINT {library}.{fk}"),
            ("drop the unique", f'ALTER TABLE {self.parent} DROP CONSTRAINT {library}."{unique}"'),
            (
                "drop the check",
                f'ALTER TABLE {self.parent} DROP CONSTRAINT {library}."{check["CONSTRAINT_NAME"]}"',
            ),
            (
                "add NEW_CODE before CODE",
                f"ALTER TABLE {self.parent} ADD COLUMN NEW_CODE VARCHAR(10) BEFORE CODE",
            ),
            ("add NEW_N before N", f"ALTER TABLE {self.parent} ADD COLUMN NEW_N INTEGER BEFORE N"),
            ("copy CODE", f"UPDATE {self.parent} SET NEW_CODE = CODE WITH NC"),
            ("copy N", f"UPDATE {self.parent} SET NEW_N = N WITH NC"),
            (
                "NEW_CODE NOT NULL",
                f"ALTER TABLE {self.parent} ALTER COLUMN NEW_CODE SET NOT NULL",
            ),
            (
                "the unique again",
                f'ALTER TABLE {self.parent} ADD CONSTRAINT {library}."{unique}" UNIQUE (NEW_CODE)',
            ),
            (
                "the foreign key again",
                f"ALTER TABLE {self.child} ADD CONSTRAINT {library}.{fk} FOREIGN KEY (P_CODE) "
                f"REFERENCES {self.parent} (NEW_CODE) ON DELETE {reference['DELETE_RULE']} "
                f"ON UPDATE {reference['UPDATE_RULE']}",
            ),
            (
                "the check again",
                f'ALTER TABLE {self.parent} ADD CONSTRAINT {library}."{check["CONSTRAINT_NAME"]}" '
                f"CHECK ({new_clause})",
            ),
            (
                "the label again",
                f"LABEL ON COLUMN {self.parent}.NEW_N IS '{str(label).strip()}'",
            ),
            ("drop CODE", f"ALTER TABLE {self.parent} DROP COLUMN CODE RESTRICT"),
            ("drop N", f"ALTER TABLE {self.parent} DROP COLUMN N RESTRICT"),
        ]
        for key, sql in steps:
            results[f"{prefix}: {key}"] = self.must(f"{prefix}: {key}", sql)


FIRST_COPY = (
    ("ADD COLUMN, copy", ("ALTER TABLE {parent} ADD COLUMN X INTEGER",)),
    ("ADD COLUMN BEFORE, copy", ("ALTER TABLE {parent} ADD COLUMN X INTEGER BEFORE CODE",)),
    (
        "DROP CHECK, ADD COLUMN, copy",
        (
            "ALTER TABLE {parent} DROP CONSTRAINT {library}.{check}",
            "ALTER TABLE {parent} ADD COLUMN X INTEGER",
        ),
    ),
    (
        "ADD COLUMN, DROP CHECK, copy",
        (
            "ALTER TABLE {parent} ADD COLUMN X INTEGER",
            "ALTER TABLE {parent} DROP CONSTRAINT {library}.{check}",
        ),
    ),
    (
        "child DROP FOREIGN KEY, ADD COLUMN, copy",
        (
            "ALTER TABLE {child} DROP CONSTRAINT {library}.{fk}",
            "ALTER TABLE {parent} ADD COLUMN X INTEGER",
        ),
    ),
    ("no DDL, copy into N", ()),
    (
        "child (outgoing foreign key): ADD COLUMN, copy",
        ("ALTER TABLE {child} ADD COLUMN X INTEGER",),
    ),
    (
        "child: DROP its FOREIGN KEY, ADD COLUMN, copy",
        (
            "ALTER TABLE {child} DROP CONSTRAINT {library}.{fk}",
            "ALTER TABLE {child} ADD COLUMN X INTEGER",
        ),
    ),
)


def first_copy(p: Probe, results: dict[str, Any], check: str, fk: str) -> None:
    """When does the first UPDATE ... WITH NC after DDL of the table work? Each case
    starts a fresh transaction and is rolled back."""
    for label, statements in FIRST_COPY:
        record: dict[str, Any] = {"ddl": []}
        for template in statements:
            sql = template.format(
                parent=p.parent, child=p.child, library=p.library, check=check, fk=fk
            )
            record["ddl"].append(p.run(label, sql)["result"])
        target = "X" if statements else "N"
        table = p.child if label.startswith("child") and "ADD COLUMN" in label else p.parent
        if label.startswith("child DROP"):
            table = p.parent
        record["copy"] = p.run(f"{label}: copy", f"UPDATE {table} SET {target} = ID WITH NC")
        results[f"0. first copy: {label}"] = record
        p.conn.rollback()


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
    print_query(journal)
    if not journal["ok"] or not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; nothing was changed")
    existing = run_query(conn, f"DJDB2I_CC* in {library}", LEFT, (library,))
    print_query(existing)
    if not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if existing["rows"]:
        raise ProbeError("check", f"DJDB2I_CC* objects exist in {library}; nothing was changed")
    if table_registry.list_path() is None:
        raise ProbeError(
            "check",
            f"{table_registry.ENV} is not set (run through scripts/pub400.sh); nothing was changed",
        )


def run(conn, library: str) -> dict[str, Any]:
    p = Probe(conn, library)
    results: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    left: Any = None
    try:
        p.create(
            PARENT,
            "ID INTEGER NOT NULL PRIMARY KEY, CODE VARCHAR(10) NOT NULL UNIQUE, "
            "N INTEGER CHECK (N >= 0)",
        )
        p.create(
            CHILD,
            f"ID INTEGER NOT NULL PRIMARY KEY, P_CODE VARCHAR(10) REFERENCES {p.parent} (CODE)",
        )
        p.must("label N", f"LABEL ON COLUMN {p.parent}.N IS 'Amount'")
        p.must("rows", f"INSERT INTO {p.parent} VALUES (1, 'a', 1), (2, 'b', 2), (3, 'c', 3)")
        p.must("rows", f"INSERT INTO {p.child} VALUES (1, 'a'), (2, 'c')")
        conn.autocommit = False
        for sql in inquiry.SUPPRESS_SQL:
            p.must("suppress CPA32B2", sql)
        conn.commit()
        results["start"] = p.state("start")
        names = p.rows(
            "constraint names",
            "SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE FROM QSYS2.SYSCST "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN (?, ?)",
            (library, PARENT, CHILD),
        )
        check = next(r["CONSTRAINT_NAME"] for r in names if r["CONSTRAINT_TYPE"] == "CHECK")
        fk = next(r["CONSTRAINT_NAME"] for r in names if r["CONSTRAINT_TYPE"] == "FOREIGN KEY")
        first_copy(p, results, f'"{check}"', f'"{fk}"')

        # a. RESTRICT while a constraint depends on the column.
        for key, sql in (
            ("a. drop CODE RESTRICT (unique, referenced)", "DROP COLUMN CODE RESTRICT"),
            ("a. drop N RESTRICT (check)", "DROP COLUMN N RESTRICT"),
        ):
            results[key] = p.run(key, f"ALTER TABLE {p.parent} {sql}")
            conn.rollback()

        # b. The copy steps, rolled back.
        p.copy(results, "b")
        conn.rollback()
        results["b. after ROLLBACK"] = p.state("b. after ROLLBACK")

        # c. The copy steps, committed.
        p.copy(results, "c")
        conn.commit()
        results["c. after COMMIT"] = p.state("c. after COMMIT")
        for key, sql in (
            ("c. child with a missing code (SQL0530?)", f"INSERT INTO {p.child} VALUES (3, 'z')"),
            ("c. duplicate code (SQL0803?)", f"INSERT INTO {p.parent} VALUES (4, 'a', 4)"),
            ("c. negative N (SQL0545?)", f"INSERT INTO {p.parent} VALUES (5, 'e', -1)"),
            ("c. a good row", f"INSERT INTO {p.parent} VALUES (6, 'f', 6)"),
        ):
            results[key] = p.run(key, sql)
            conn.rollback()
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        with contextlib.suppress(Exception):
            p.run("discard the QAQQINI copy", inquiry.DISCARD_SQL)
        conn.autocommit = True
        for table in (CHILD, PARENT):
            if p.exists(table):
                dropped = p.run(f"drop {table}", f"DROP TABLE {library}.{table} RESTRICT")
                cleanup[table] = dropped["result"]
        found = run_query(conn, f"left in {library}", LEFT, (library,))
        print_query(found)
        left = found["rows"] if found["ok"] else "error"
        if left:
            print(f"\nWARNING: objects may be left: {left}", file=sys.stderr)
    print("\nSummary")
    for key, record in results.items():
        if isinstance(record, dict) and "result" in record:
            print(f"  {key}: {record['result']}")
    return {"results": results, "cleanup": cleanup, "left": left, "statements": p.steps}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, change and drop the tables")
    args = parser.parse_args(argv)
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is needed", 1)
        conn = connect(
            settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1", "DBQ": library}, autocommit=True
        )
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('lib_column_copy', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
