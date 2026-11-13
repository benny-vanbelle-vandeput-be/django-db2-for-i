"""GROUP BY a primary key alone, with other columns selected (#258 E).

``allows_group_by_selected_pks`` lets Django group by a model's primary key alone
while it selects the model's other columns. probe ``phase7_flags`` found SQL0122 with
a unique index in QTEMP; a primary key needs a journaled library, hence this probe.

THIS CHANGES THE IBM i, in the default library (DB2I_DEFAULT_LIBRARY, the journaled
test library) only: tables DJDB2I_GBP (ID INTEGER NOT NULL PRIMARY KEY, NAME
VARCHAR(10), N INTEGER) and DJDB2I_GBC (ID INTEGER NOT NULL PRIMARY KEY, P_ID
INTEGER), each recorded on the cleanup list (tests/table_registry.py) before its
CREATE TABLE; 2 rows in DJDB2I_GBP and 3 in DJDB2I_GBC. No other index.

Approval: issue #258 (comment 6864673390). At the end, also after a failure: both
tables dropped, and a check that no DJDB2I_GB* object is left.

Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_group_by_pk              # dry run: checks only
    bin/probe --approved <link> lib_group_by_pk -- --execute

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

PARENT = "DJDB2I_GBP"
CHILD = "DJDB2I_GBC"
OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"
LEFT = (
    "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X "
    "WHERE OBJNAME LIKE 'DJDB2I_GB%' OR OBJLONGNAME LIKE 'DJDB2I_GB%'"
)


def sqlcode(message: str) -> str:
    match = re.search(r"\((-?\d+)\)", message)
    return match.group(1) if match else "?"


class Probe:
    def __init__(self, conn, library: str):
        self.conn = conn
        self.library = library
        self.registry = table_registry.list_path()
        self.steps: list[dict[str, Any]] = []

    def run(self, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
        result = run_statement(self.conn, label, sql, params)
        self.steps.append(result)
        return result

    def query(self, label: str, sql: str) -> dict[str, Any]:
        result = run_query(self.conn, label, sql)
        print_query(result)
        if result["ok"]:
            return {"sql": sql, "result": "ok", "rows": result["rows"]}
        return {
            "sql": sql,
            "result": sqlcode(result.get("message", "")),
            "sqlstate": result.get("sqlstate", ""),
            "message": result.get("message", "")[:200],
        }

    def exists(self, name: str) -> bool:
        result = run_query(self.conn, f"{name} exists", OBJECTS, (self.library, name))
        return bool(result["ok"] and result["rows"])

    def create(self, table: str, body: str) -> None:
        sql = f"CREATE TABLE {self.library}.{table} ({body})"
        entry = table_registry.parse(sql, self.library)
        assert entry is not None and (entry.library, entry.name) == (self.library, table)
        table_registry.record(self.registry, entry)
        if not self.run(f"create {table}", sql)["ok"]:
            raise ProbeError("refused", f"create {table} failed")


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
    existing = run_query(conn, f"DJDB2I_GB* in {library}", LEFT, (library,))
    print_query(existing)
    if not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if existing["rows"]:
        raise ProbeError("check", f"DJDB2I_GB* objects exist in {library}; nothing was changed")
    if table_registry.list_path() is None:
        raise ProbeError(
            "check",
            f"{table_registry.ENV} is not set (run through scripts/pub400.sh); nothing was changed",
        )


def run(conn, library: str) -> dict[str, Any]:
    p = Probe(conn, library)
    parent, child = f"{library}.{PARENT}", f"{library}.{CHILD}"
    cases: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    left: Any = None
    try:
        p.create(PARENT, "ID INTEGER NOT NULL PRIMARY KEY, NAME VARCHAR(10), N INTEGER")
        p.create(CHILD, "ID INTEGER NOT NULL PRIMARY KEY, P_ID INTEGER")
        p.run("rows", f"INSERT INTO {parent} VALUES (1, 'one', 10), (2, 'two', 20)")
        p.run("rows", f"INSERT INTO {child} VALUES (1, 1), (2, 1), (3, 2)")
        cases["one table: GROUP BY the key, NAME selected"] = p.query(
            "one table",
            f"SELECT {parent}.ID, {parent}.NAME, SUM({parent}.N) FROM {parent} "
            f"GROUP BY {parent}.ID ORDER BY 1",
        )
        cases["join: GROUP BY the parent key, NAME selected"] = p.query(
            "join",
            f"SELECT {parent}.ID, {parent}.NAME, COUNT({child}.ID) FROM {parent} "
            f"LEFT OUTER JOIN {child} ON ({parent}.ID = {child}.P_ID) "
            f"GROUP BY {parent}.ID ORDER BY 1",
        )
        cases["control: every selected column in GROUP BY"] = p.query(
            "control",
            f"SELECT {parent}.ID, {parent}.NAME, COUNT({child}.ID) FROM {parent} "
            f"LEFT OUTER JOIN {child} ON ({parent}.ID = {child}.P_ID) "
            f"GROUP BY {parent}.ID, {parent}.NAME ORDER BY 1",
        )
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        for table in (CHILD, PARENT):
            if p.exists(table):
                dropped = p.run(f"drop {table}", f"DROP TABLE {library}.{table} RESTRICT")
                cleanup[table] = dropped["ok"] or dropped.get("message", "")[:160]
        left = run_query(conn, f"left in {library}", LEFT, (library,))
        print_query(left)
        left = left["rows"] if left["ok"] else "error"
        if left:
            print(f"\nWARNING: objects may be left: {left}", file=sys.stderr)
    print("\nSummary")
    for label, record in cases.items():
        print(f"  {label}: {record.get('result')}")
    return {"cases": cases, "cleanup": cleanup, "left": left, "statements": p.steps}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the tables")
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
        print(f"\nresult saved to {write_result('lib_group_by_pk', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
