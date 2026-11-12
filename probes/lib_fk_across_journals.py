"""Foreign keys between tables in two libraries with their own journals (phase 7, step 4).

THIS CHANGES THE IBM i: table DJDB2I_XJP in the journaled default library and table
DJDB2I_XJC in the journaled other library, recorded on the cleanup list
(tests/table_registry.py) before their CREATE TABLE and dropped at the end, also after a
failure: the child first, then the parent, each with RESTRICT. On them, one at a time,
each dropped before the next: a foreign key <other>.DJDB2I_XJC_FK from DJDB2I_XJC.P_ID
to <default>.DJDB2I_XJP.ID with each delete rule.

Approval request: issue #249. Per rule: 2 parents and a child of each, delete parent 2,
read both tables, ROLLBACK. For CASCADE one more round that COMMITs, then deletes its
rows (and commits). The journal of each table is read first and recorded.
`lib_on_delete` (#220) could not answer this: its tables shared one journal.

Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_fk_across_journals              # dry run: checks only
    bin/probe --approved <link> lib_fk_across_journals -- --execute

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

PARENT = "DJDB2I_XJP"
CHILD = "DJDB2I_XJC"
FK = "DJDB2I_XJC_FK"
RULES = ("NO ACTION", "RESTRICT", "CASCADE", "SET NULL")
OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"
JOURNAL = (
    "SELECT JOURNAL_LIBRARY, JOURNAL_NAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"
)


def sqlcode(message: str) -> str:
    match = re.search(r"\((-?\d+)\)", message)
    return match.group(1) if match else "?"


class Probe:
    def __init__(self, conn, default: str, other: str):
        self.conn = conn
        self.default = default
        self.other = other
        self.parent = f"{default}.{PARENT}"
        self.child = f"{other}.{CHILD}"
        self.fk = f"{other}.{FK}"
        self.registry = table_registry.list_path()
        self.steps: list[dict[str, Any]] = []

    def run(self, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
        result = run_statement(self.conn, label, sql, params)
        self.steps.append(result)
        return result

    def outcome(self, label: str, sql: str, params: tuple = ()) -> str:
        result = self.run(label, sql, params)
        return "ok" if result["ok"] else sqlcode(result.get("message", ""))

    def rows(self, label: str, sql: str, params: tuple = ()) -> list[dict[str, Any]] | str:
        result = run_query(self.conn, label, sql, params)
        print_query(result)
        if not result["ok"]:
            return f"error {result.get('sqlstate')} {result.get('message', '')[:120]}"
        return result["rows"]

    def exists(self, library: str, table: str) -> bool:
        result = run_query(self.conn, f"{library}.{table} exists", OBJECTS, (library, table))
        return bool(result["ok"] and result["rows"])

    def create(self, library: str, table: str, body: str) -> None:
        sql = f"CREATE TABLE {library}.{table} ({body})"
        entry = table_registry.parse(sql, self.default)
        assert entry is not None and (entry.library, entry.name) == (library, table)
        table_registry.record(self.registry, entry)
        if not self.run(f"create {library}.{table}", sql)["ok"]:
            raise ProbeError("refused", f"create {library}.{table} failed; nothing else was run")

    def journals(self) -> dict[str, Any]:
        return {
            f"{library}.{table}": self.rows(f"journal of {table}", JOURNAL, (library, table))
            for library, table in ((self.default, PARENT), (self.other, CHILD))
        }

    def round(self, delete: int, commit: bool) -> dict[str, Any]:
        """Two parents, a child of each, delete one parent, read both tables; then
        ROLLBACK, or COMMIT and delete the rows again."""
        self.conn.autocommit = False
        record: dict[str, Any] = {"ends with": "COMMIT" if commit else "ROLLBACK"}
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
            result = self.run(
                f"delete parent {delete}", f"DELETE FROM {self.parent} WHERE ID = ?", (delete,)
            )
            record["delete"] = "ok" if result["ok"] else sqlcode(result.get("message", ""))
            if not result["ok"]:
                record["delete message"] = result.get("message", "")[:200]
            record["parents after"] = self.rows(
                "parents after", f"SELECT ID FROM {self.parent} ORDER BY ID"
            )
            record["children after"] = self.rows(
                "children after", f"SELECT ID, P_ID FROM {self.child} ORDER BY ID"
            )
            if commit:
                record["commit"] = "ok"
                try:
                    self.conn.commit()
                except Exception as exc:  # recorded, the probe goes on
                    record["commit"] = f"error {exc!s:.160}"
                record["after commit, children"] = self.rows(
                    "children after commit", f"SELECT ID, P_ID FROM {self.child} ORDER BY ID"
                )
                record["empty again"] = [
                    self.outcome("delete children", f"DELETE FROM {self.child}"),
                    self.outcome("delete parents", f"DELETE FROM {self.parent}"),
                ]
                self.conn.commit()
        finally:
            record["rollback"] = "ok"
            try:
                self.conn.rollback()
            except Exception as exc:  # recorded, the probe goes on
                record["rollback"] = f"error {exc!s:.120}"
            self.conn.autocommit = True
        return record

    def case(self, rule: str) -> dict[str, Any]:
        print(f"\n======== ON DELETE {rule} ========")
        ddl = (
            f"ALTER TABLE {self.child} ADD CONSTRAINT {self.fk} FOREIGN KEY (P_ID) "
            f"REFERENCES {self.parent} (ID) ON DELETE {rule}"
        )
        made = self.run(f"add {rule}", ddl)
        record: dict[str, Any] = {"ddl": ddl, "ok": made["ok"]}
        if not made["ok"]:
            record["sqlstate"] = made.get("sqlstate", "")
            record["message"] = made.get("message", "")[:200]
            return record
        record["catalog"] = self.rows(
            "SYSREFCST",
            "SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME, UNIQUE_CONSTRAINT_SCHEMA, DELETE_RULE "
            "FROM QSYS2.SYSREFCST WHERE CONSTRAINT_SCHEMA = ? AND CONSTRAINT_NAME = ?",
            (self.other, FK),
        )
        record["rolled back"] = self.round(2, commit=False)
        if rule == "CASCADE":
            record["committed"] = self.round(2, commit=True)
        dropped = self.run(f"drop {rule}", f"ALTER TABLE {self.child} DROP CONSTRAINT {self.fk}")
        record["dropped"] = dropped["ok"] or dropped.get("message", "")[:120]
        return record


def checks(conn, default: str, other: str) -> None:
    schema = run_query(conn, "CURRENT SCHEMA", "SELECT CURRENT SCHEMA AS S FROM SYSIBM.SYSDUMMY1")
    print_query(schema)
    if not schema["ok"] or [row.get("S") for row in schema["rows"]] != [default]:
        raise ProbeError("check", "CURRENT SCHEMA is not the default library; nothing was changed")
    for library, table in ((default, PARENT), (other, CHILD)):
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
        existing = run_query(conn, f"{table} exists already", OBJECTS, (library, table))
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


def run(conn, default: str, other: str) -> dict[str, Any]:
    p = Probe(conn, default, other)
    cases: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    journals: dict[str, Any] = {}
    try:
        p.create(default, PARENT, "ID INTEGER NOT NULL PRIMARY KEY")
        p.create(other, CHILD, "ID INTEGER NOT NULL PRIMARY KEY, P_ID INTEGER")
        journals = p.journals()
        for rule in RULES:
            cases[rule] = p.case(rule)
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        for library, table in ((other, CHILD), (default, PARENT)):
            if p.exists(library, table):
                dropped = p.run(f"drop {table}", f"DROP TABLE {library}.{table} RESTRICT")
                cleanup[f"{library}.{table}"] = dropped["ok"] or dropped.get("message", "")[:160]
        left = [
            f"{library}.{table}"
            for library, table in ((default, PARENT), (other, CHILD))
            if p.exists(library, table)
        ]
        if left:
            print(f"\nWARNING: {left} may be left", file=sys.stderr)
    print("\nSummary")
    for rule, record in cases.items():
        rolled = record.get("rolled back", {})
        print(f"  {rule}: add {record.get('ok')}, delete {rolled.get('delete', record)}")
    return {
        "journals": journals,
        "cases": cases,
        "cleanup": cleanup,
        "left": left,
        "statements": p.steps,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the tables")
    args = parser.parse_args(argv)
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        default, other = settings.default_library, settings.other_library
        if not default or not other:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY and DB2I_OTHER_LIBRARY are needed", 1)
        conn = connect(
            settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1", "DBQ": default}, autocommit=True
        )
        checks(conn, default, other)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, default, other)
        print(f"\nresult saved to {write_result('lib_fk_across_journals', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
