"""The delete rules of a foreign key, for phase 6 (Django 6.1's DB-level on_delete; issue #220).

THIS CHANGES THE IBM i: two tables, DJDB2I_P6DELP and DJDB2I_P6DELC, in the journaled
default library, recorded on the cleanup list (tests/table_registry.py) before their
CREATE TABLE and dropped at the end, also after a failure. On them, one at a time, each
dropped before the next: a foreign key with each delete rule.

Approved by the maintainer on issue #220 (comment 6554356422) with three points:

- Final cleanup: the child table first, then the parent, each with RESTRICT.
- SET DEFAULT: the default P_ID = 1 points to parent 1, so the normal case deletes parent
  2. Deleting parent 1 is a separate case: what happens when the default has no parent.
- Both tables share one journal, so this probe cannot answer the different-journal case.
  The result records it as open.

Each case's inserts and delete run in their own transaction, ended with ROLLBACK before
the next DDL (the condition from #213). Run only through the PUB400 lock. Not part of
probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_on_delete              # dry run: checks only
    bin/probe --approved <link> lib_on_delete -- --execute

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
from tests import table_registry

PARENT = "DJDB2I_P6DELP"
CHILD = "DJDB2I_P6DELC"
FK = "DJDB2I_P6DELC_FK"
PROBE_OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"

# name, the rule, the parent to delete.
CASES = (
    ("NO ACTION", "NO ACTION", 2),
    ("RESTRICT", "RESTRICT", 2),
    ("CASCADE", "CASCADE", 2),
    ("SET NULL", "SET NULL", 2),
    ("SET DEFAULT, parent 2 (the default's parent stays)", "SET DEFAULT", 2),
    ("SET DEFAULT, parent 1 (the default has no parent then)", "SET DEFAULT", 1),
)
OPEN_QUESTIONS = (
    "Foreign keys between tables in different journals: both tables here share the library's "
    "QSQJRN, so this probe cannot answer that (the maintainer's point on #220). Open."
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
        return result

    def outcome(self, label: str, sql: str, params: tuple = ()) -> str:
        result = self.run(label, sql, params)
        return "ok" if result["ok"] else sqlcode(result.get("message", ""))

    def rows(self, label: str, sql: str, params: tuple) -> list[dict[str, Any]] | str:
        result = run_query(self.conn, label, sql, params)
        print_query(result)
        if not result["ok"]:
            return f"error {result.get('sqlstate')} {result.get('message', '')[:120]}"
        return result["rows"]

    def exists(self, table: str) -> bool:
        result = run_query(self.conn, f"{table} exists", PROBE_OBJECTS, (self.library, table))
        return bool(result["ok"] and result["rows"])

    def create(self, table: str, body: str) -> None:
        sql = f"CREATE TABLE {self.library}.{table} ({body})"
        entry = table_registry.parse(sql, self.library)
        assert entry is not None and entry.name == table
        table_registry.record(self.registry, entry)
        if not self.run(f"create {table}", sql)["ok"]:
            raise ProbeError("refused", f"create {table} failed; nothing else was run")

    def catalog(self) -> dict[str, Any]:
        """The catalog rows of these tables and this constraint only."""
        return {
            "SYSCST": self.rows(
                "SYSCST",
                "SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE FROM QSYS2.SYSCST "
                "WHERE TABLE_SCHEMA = ? AND TABLE_NAME IN (?, ?) ORDER BY CONSTRAINT_NAME",
                (self.library, PARENT, CHILD),
            ),
            "SYSREFCST": self.rows(
                "SYSREFCST",
                "SELECT CONSTRAINT_NAME, UNIQUE_CONSTRAINT_NAME, UPDATE_RULE, DELETE_RULE "
                "FROM QSYS2.SYSREFCST WHERE CONSTRAINT_SCHEMA = ? AND CONSTRAINT_NAME = ?",
                (self.library, FK),
            ),
            "SYSKEYCST": self.rows(
                "SYSKEYCST",
                "SELECT COLUMN_NAME, ORDINAL_POSITION FROM QSYS2.SYSKEYCST "
                "WHERE CONSTRAINT_SCHEMA = ? AND CONSTRAINT_NAME = ? ORDER BY ORDINAL_POSITION",
                (self.library, FK),
            ),
        }

    def transaction(self, delete: int) -> dict[str, Any]:
        """Two parents, a child of each, delete one parent, read the children; ended with
        ROLLBACK before the next DDL."""
        self.conn.autocommit = False
        record: dict[str, Any] = {}
        try:
            inserts = {}
            for parent in (1, 2):
                inserts[f"parent {parent}"] = self.outcome(
                    f"parent {parent}", f"INSERT INTO {self.parent} (ID) VALUES (?)", (parent,)
                )
            for child, parent in ((10, 1), (20, 2)):
                inserts[f"child {child}"] = self.outcome(
                    f"child {child} of {parent}",
                    f"INSERT INTO {self.child} (ID, P_ID) VALUES (?, ?)",
                    (child, parent),
                )
            record["inserts"] = inserts
            record["deleted parent"] = delete
            result = self.run(
                f"delete parent {delete}", f"DELETE FROM {self.parent} WHERE ID = ?", (delete,)
            )
            record["delete"] = "ok" if result["ok"] else sqlcode(result.get("message", ""))
            if not result["ok"]:
                record["delete sqlstate"] = result.get("sqlstate", "")
                record["delete message"] = result.get("message", "")[:200]
            record["parents after"] = self.rows(
                "parents after", f"SELECT ID FROM {self.parent} WHERE ID > ? ORDER BY ID", (0,)
            )
            record["children after"] = self.rows(
                "children after",
                f"SELECT ID, P_ID FROM {self.child} WHERE ID > ? ORDER BY ID",
                (0,),
            )
        finally:
            record["rollback"] = "ok"
            try:
                self.conn.rollback()
            except Exception as exc:  # recorded, the probe goes on
                record["rollback"] = f"error {exc!s:.120}"
            self.conn.autocommit = True
        return record

    def case(self, number: int, name: str, rule: str, delete: int) -> dict[str, Any]:
        print(f"\n======== {number}. {name} ========")
        ddl = (
            f"ALTER TABLE {self.child} ADD CONSTRAINT {FK} FOREIGN KEY (P_ID) "
            f"REFERENCES {self.parent} (ID) ON DELETE {rule}"
        )
        made = self.run(f"add {rule}", ddl)
        record: dict[str, Any] = {"ddl": ddl, "ok": made["ok"]}
        if not made["ok"]:
            record["sqlstate"] = made.get("sqlstate", "")
            record["message"] = made.get("message", "")[:200]
            return record
        record["catalog"] = self.catalog()
        record.update(self.transaction(delete))
        dropped = self.run(f"drop {rule}", f"ALTER TABLE {self.child} DROP CONSTRAINT {FK}")
        record["dropped"] = dropped["ok"] or dropped.get("message", "")[:120]
        return record


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
    if not journal["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; nothing was changed")
    for table in (PARENT, CHILD):
        existing = run_query(conn, f"{table} exists already", PROBE_OBJECTS, (library, table))
        print_query(existing)
        if not existing["ok"]:
            raise ProbeError("check", "pre-checks could not run; nothing was changed")
        if existing["rows"]:
            raise ProbeError("check", f"{table} exists in {library}; nothing was changed")
    if table_registry.list_path() is None:
        raise ProbeError(
            "check",
            f"{table_registry.ENV} is not set (run through scripts/pub400.sh); nothing was changed",
        )


def run(conn, library: str) -> dict[str, Any]:
    p = Probe(conn, library)
    cases: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    try:
        p.create(PARENT, "ID INTEGER NOT NULL PRIMARY KEY")
        p.create(CHILD, "ID INTEGER NOT NULL PRIMARY KEY, P_ID INTEGER DEFAULT 1")
        for number, (name, rule, delete) in enumerate(CASES, 1):
            cases[f"{number}. {name}"] = p.case(number, name, rule, delete)
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        # The maintainer's order on #220: the child first, then the parent, with RESTRICT.
        for table in (CHILD, PARENT):
            if p.exists(table):
                dropped = p.run(f"drop {table}", f"DROP TABLE {library}.{table} RESTRICT")
                cleanup[table] = dropped["ok"] or dropped.get("message", "")[:160]
        left = [table for table in (PARENT, CHILD) if p.exists(table)]
        if left:
            print(f"\nWARNING: {left} may be left in {library}", file=sys.stderr)
    print("\nSummary")
    for label, record in cases.items():
        print(f"  {label}: delete {record.get('delete', record)}")
    return {
        "cases": cases,
        "cleanup": cleanup,
        "left": left,
        "open": OPEN_QUESTIONS,
        "statements": p.steps,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the tables")
    args = parser.parse_args(argv)
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        conn = connect(
            settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1", "DBQ": library}, autocommit=True
        )
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('lib_on_delete', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
