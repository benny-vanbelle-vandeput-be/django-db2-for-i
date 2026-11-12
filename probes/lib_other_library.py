"""Constraints and indexes on a table in another library than NAME (#124, phase 7 step 4).

THIS CHANGES THE IBM i: tables DJDB2I_OLP and DJDB2I_OLC in the journaled other library,
recorded on the cleanup list (tests/table_registry.py) before their CREATE TABLE; and,
one at a time, each dropped again before the next, constraints and indexes on
DJDB2I_OLC: a foreign key, a UNIQUE and a CHECK constraint, each with an unqualified
and a qualified name, and the index DJDB2I_OLIX unqualified (it may land in the default
library), qualified with the other library, and DJDB2I_OLIX2 qualified with the default
library. The connection's current schema is the default library, as the backend's.
No data rows.

Approval request: issue #124. At the end, also after a failure: each index explicitly
(in whichever library it landed), then DJDB2I_OLC, then DJDB2I_OLP, and a check that no
DJDB2I_OL* object is left in either library.

Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_other_library              # dry run: checks only
    bin/probe --approved <link> lib_other_library -- --execute

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

PARENT = "DJDB2I_OLP"
CHILD = "DJDB2I_OLC"
INDEX = "DJDB2I_OLIX"
INDEX_DEFAULT = "DJDB2I_OLIX2"
OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"
LEFT = (
    "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X "
    "WHERE OBJNAME LIKE 'DJDB2I_OL%' OR OBJLONGNAME LIKE 'DJDB2I_OL%'"
)


def sqlcode(message: str) -> str:
    match = re.search(r"\((-?\d+)\)", message)
    return match.group(1) if match else "?"


class Probe:
    def __init__(self, conn, default: str, other: str):
        self.conn = conn
        self.default = default
        self.other = other
        self.child = f"{other}.{CHILD}"
        self.registry = table_registry.list_path()
        self.steps: list[dict[str, Any]] = []

    def run(self, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
        result = run_statement(self.conn, label, sql, params)
        self.steps.append(result)
        return result

    def outcome(self, label: str, sql: str) -> dict[str, Any]:
        result = self.run(label, sql)
        if result["ok"]:
            return {"sql": sql, "result": "ok"}
        return {
            "sql": sql,
            "result": sqlcode(result.get("message", "")),
            "sqlstate": result.get("sqlstate", ""),
            "message": result.get("message", "")[:200],
        }

    def rows(self, label: str, sql: str, params: tuple = ()) -> list[dict[str, Any]] | str:
        result = run_query(self.conn, label, sql, params)
        print_query(result)
        if not result["ok"]:
            return f"error {result.get('sqlstate')} {result.get('message', '')[:120]}"
        return result["rows"]

    def exists(self, library: str, name: str) -> bool:
        result = run_query(self.conn, f"{library}.{name} exists", OBJECTS, (library, name))
        return bool(result["ok"] and result["rows"])

    def create(self, table: str, body: str) -> None:
        sql = f"CREATE TABLE {self.other}.{table} ({body})"
        entry = table_registry.parse(sql, self.default)
        assert entry is not None and (entry.library, entry.name) == (self.other, table)
        table_registry.record(self.registry, entry)
        if not self.run(f"create {self.other}.{table}", sql)["ok"]:
            raise ProbeError("refused", f"create {table} failed; nothing else was run")

    def constraint(self, label: str, name: str, body: str) -> dict[str, Any]:
        """ADD CONSTRAINT <name> <body>; where it landed; DROP CONSTRAINT again."""
        record = self.outcome(
            f"{label}: add", f"ALTER TABLE {self.child} ADD CONSTRAINT {name} {body}"
        )
        if record["result"] == "ok":
            bare = name.split(".")[-1]
            record["catalog"] = self.rows(
                f"{label}: SYSCST",
                "SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME, TABLE_SCHEMA, TABLE_NAME, "
                "CONSTRAINT_TYPE FROM QSYS2.SYSCST WHERE CONSTRAINT_NAME = ? "
                "AND CONSTRAINT_SCHEMA IN (?, ?)",
                (bare, self.default, self.other),
            )
            record["drop"] = self.outcome(
                f"{label}: drop", f"ALTER TABLE {self.child} DROP CONSTRAINT {name}"
            )
        return record

    def index(self, label: str, name: str) -> dict[str, Any]:
        """CREATE INDEX <name> ON the child; where it landed; DROP INDEX again."""
        record = self.outcome(f"{label}: create", f"CREATE INDEX {name} ON {self.child} (NAME)")
        if record["result"] == "ok":
            bare = name.split(".")[-1]
            record["catalog"] = self.rows(
                f"{label}: SYSINDEXES",
                "SELECT INDEX_SCHEMA, INDEX_NAME, TABLE_SCHEMA, TABLE_NAME FROM QSYS2.SYSINDEXES "
                "WHERE INDEX_NAME = ? AND INDEX_SCHEMA IN (?, ?)",
                (bare, self.default, self.other),
            )
            record["in default"] = self.exists(self.default, bare)
            record["in other"] = self.exists(self.other, bare)
            for where, library in (("default", self.default), ("other", self.other)):
                if self.exists(library, bare):
                    record[f"drop in {where}"] = self.outcome(
                        f"{label}: drop", f"DROP INDEX {library}.{bare}"
                    )
        return record


def checks(conn, default: str, other: str) -> None:
    schema = run_query(conn, "CURRENT SCHEMA", "SELECT CURRENT SCHEMA AS S FROM SYSIBM.SYSDUMMY1")
    print_query(schema)
    if not schema["ok"] or [row.get("S") for row in schema["rows"]] != [default]:
        raise ProbeError("check", "CURRENT SCHEMA is not the default library; nothing was changed")
    journal = run_query(
        conn,
        f"{other}: QSQJRN journal",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) X",
        (other,),
    )
    print_query(journal)
    if not journal["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{other} has no QSQJRN journal; nothing was changed")
    for library in (default, other):
        existing = run_query(conn, f"DJDB2I_OL* in {library}", LEFT, (library,))
        print_query(existing)
        if not existing["ok"]:
            raise ProbeError("check", "pre-checks could not run; nothing was changed")
        if existing["rows"]:
            raise ProbeError("check", f"DJDB2I_OL* objects exist in {library}; nothing was changed")
    if table_registry.list_path() is None:
        raise ProbeError(
            "check",
            f"{table_registry.ENV} is not set (run through scripts/pub400.sh); nothing was changed",
        )


def run(conn, default: str, other: str) -> dict[str, Any]:
    p = Probe(conn, default, other)
    cases: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    try:
        p.create(PARENT, "ID INTEGER NOT NULL PRIMARY KEY")
        p.create(CHILD, "ID INTEGER NOT NULL PRIMARY KEY, P_ID INTEGER, NAME VARCHAR(20)")
        references = f"FOREIGN KEY (P_ID) REFERENCES {other}.{PARENT} (ID)"
        for kind, body in (
            ("foreign key", references),
            ("unique", "UNIQUE (NAME)"),
            ("check", "CHECK (ID > 0)"),
        ):
            name = f"DJDB2I_OLC_{kind.split()[0].upper()[:5]}"
            cases[f"{kind}, unqualified"] = p.constraint(f"{kind}, unqualified", name, body)
            cases[f"{kind}, qualified"] = p.constraint(
                f"{kind}, qualified", f"{other}.{name}", body
            )
        cases["index, unqualified"] = p.index("index, unqualified", INDEX)
        cases["index, qualified with other"] = p.index("index, other", f"{other}.{INDEX}")
        cases["index, qualified with default"] = p.index(
            "index, default", f"{default}.{INDEX_DEFAULT}"
        )
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        for library in (default, other):
            for index in (INDEX, INDEX_DEFAULT):
                if p.exists(library, index):
                    dropped = p.run(f"drop {library}.{index}", f"DROP INDEX {library}.{index}")
                    cleanup[f"{library}.{index}"] = dropped["ok"] or dropped.get("message", "")
        for table in (CHILD, PARENT):
            if p.exists(other, table):
                dropped = p.run(f"drop {table}", f"DROP TABLE {other}.{table} RESTRICT")
                cleanup[f"{other}.{table}"] = dropped["ok"] or dropped.get("message", "")[:160]
        left = {
            library: p.rows(f"left in {library}", LEFT, (library,)) for library in (default, other)
        }
        if any(left.values()):
            print(f"\nWARNING: objects may be left: {left}", file=sys.stderr)
    print("\nSummary")
    for label, record in cases.items():
        print(f"  {label}: {record.get('result')}")
    return {"cases": cases, "cleanup": cleanup, "left": left, "statements": p.steps}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the objects")
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
        print(f"\nresult saved to {write_result('lib_other_library', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
