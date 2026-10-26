"""Which statements before an ALTER TABLE in the same transaction cause SQL0910
(SQL0910 follow-up after #172).

THIS CHANGES THE IBM i: one table, DJPRB910, in the journaled default
library, recorded on the cleanup list (tests/table_registry.py) before each
CREATE TABLE and dropped at the end (DROP TABLE ... RESTRICT), also after a
failure. In QTEMP and the probe's own job only: the job's QAQQINI copy with
SUPPRESS_INQUIRY_MESSAGES *YES (QSYS2.OVERRIDE_QAQQINI 1 and 2, discarded with
3 at the end), so SET NOT NULL runs as it does in a migration. Approved by the
maintainer on 2026-10-26 on issue #173 under these conditions: DJPRB910 on
the cleanup list before the CREATE; the only PUB400 connection (the lock);
started via bin/probe --approved <link>. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_pending_change              # dry run: checks only
    bin/probe --approved <link> lib_pending_change -- --execute

Each step starts from a fresh DJPRB910 with three rows without NULLs
(autocommit on), runs its statements with autocommit off and rolls back:
1. control: a fourth row with C NULL (committed before the transaction);
   UPDATE ... WHERE C IS NULL (1 row), then SET NOT NULL;
2. UPDATE ... WHERE C IS NULL (0 rows), then SET NOT NULL;
3. SELECT 1 ... WHERE C IS NULL FETCH FIRST 1 ROW ONLY, then SET NOT NULL;
4. LOCK TABLE ... IN EXCLUSIVE MODE, the SELECT of step 3, then SET NOT NULL.
The UPDATE and ALTER are the statements of golden ddl/alter_field_not_null.
The job's inquiry message reply must be *RQD, so if the suppression did not
apply, CPA32B2 cancels the statement instead of waiting. Every catalog query
is limited to the probe's own table.
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
from django_db2_for_i import inquiry
from tests import table_registry

T = "DJPRB910"
BODY = "ID INTEGER NOT NULL PRIMARY KEY, C INTEGER"
PROBE_OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"


class Probe:
    def __init__(self, conn, library: str):
        self.conn = conn
        self.library = library
        self.table = f"{library}.{T}"
        self.registry = table_registry.list_path()
        self.steps: list[dict[str, Any]] = []

    def run(self, label: str, sql: str) -> dict[str, Any]:
        result = run_statement(self.conn, label, sql)
        self.steps.append(result)
        return result

    def scalar(self, sql: str, params: tuple = ()) -> Any:
        result = run_query(self.conn, "check", sql, params)
        if not result["ok"]:
            return f"error {result.get('sqlstate')}"
        rows = result["rows"]
        return next(iter(rows[0].values())) if rows else None

    def exists(self) -> bool:
        return bool(
            self.scalar(
                "SELECT COUNT(*) FROM QSYS2.SYSTABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
                (self.library, T),
            )
        )

    def nullable(self) -> Any:
        return self.scalar(
            "SELECT IS_NULLABLE FROM QSYS2.SYSCOLUMNS "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND COLUMN_NAME = 'C'",
            (self.library, T),
        )

    def fresh(self) -> None:
        """A fresh DJPRB910 with three rows without NULLs, autocommit on."""
        self.conn.autocommit = True
        if self.exists():
            self.run(f"drop {T}", f"DROP TABLE {self.table} RESTRICT")
        sql = f"CREATE TABLE {self.table} ({BODY})"
        entry = table_registry.parse(sql, self.library)
        assert entry is not None and entry.name == T
        table_registry.record(self.registry, entry)
        if not self.run(f"create {T}", sql)["ok"]:
            raise ProbeError("refused", f"create {T} failed")
        self.run("rows", f"INSERT INTO {self.table} (ID, C) VALUES (1, 1), (2, 2), (3, 3)")

    def step(
        self, number: int, label: str, statements: list[str], null_row: bool = False
    ) -> dict[str, Any]:
        print(f"\n======== {number}. {label} ========")
        self.fresh()
        if null_row:
            self.run("NULL row (committed)", f"INSERT INTO {self.table} (ID, C) VALUES (4, NULL)")
        self.conn.autocommit = False
        outcomes = []
        for sql in statements:
            result = self.run(label, sql)
            outcome: dict[str, Any] = {"sql": sql, "ok": result["ok"]}
            if result["ok"]:
                if sql.startswith("UPDATE"):
                    outcome["rows changed"] = result["rowcount"]
            else:
                outcome["sqlstate"] = result.get("sqlstate", "")
                outcome["message"] = result.get("message", "")[:200]
            outcomes.append(outcome)
        rollback = "ok"
        try:
            self.conn.rollback()
        except Exception as exc:  # recorded, the probe goes on
            rollback = f"error {exc!s:.120}"
        self.conn.autocommit = True
        record = {
            "statements": outcomes,
            "rollback": rollback,
            "C nullable after rollback": self.nullable(),
            "rows with C NULL after rollback": self.scalar(
                f"SELECT COUNT(*) FROM {self.table} WHERE C IS NULL"
            ),
        }
        print(f"  {record}")
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
    existing = run_query(conn, f"{library}: {T} exists already", PROBE_OBJECTS, (library, T))
    for result in (journal, existing):
        print_query(result)
    if not journal["ok"] or not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; nothing was changed")
    if existing["rows"]:
        raise ProbeError("check", f"{T} exists in {library}; nothing was changed")
    if table_registry.list_path() is None:
        raise ProbeError(
            "check",
            f"{table_registry.ENV} is not set (run through scripts/pub400.sh); nothing was changed",
        )
    cursor = conn.cursor()
    try:
        reply = inquiry.read_reply(cursor)
    finally:
        cursor.close()
    print(f"\ninquiry message reply: {reply}")
    if reply != "*RQD":
        raise ProbeError(
            "check", f"the inquiry message reply is {reply}, not *RQD; nothing was changed"
        )


def run(conn, library: str) -> dict[str, Any]:
    p = Probe(conn, library)
    table = p.table
    update = f'UPDATE {table} SET "C" = -1 WHERE "C" IS NULL'
    select = f'SELECT 1 FROM {table} WHERE "C" IS NULL FETCH FIRST 1 ROW ONLY'
    alter = f'ALTER TABLE {table} ALTER COLUMN "C" SET NOT NULL'
    steps: dict[str, Any] = {}
    try:
        print("\n======== suppression (QTEMP, own job) ========")
        suppression = [p.run("suppress", sql) for sql in inquiry.SUPPRESS_SQL]
        if not all(result["ok"] for result in suppression):
            raise ProbeError("refused", "OVERRIDE_QAQQINI failed; no step was run")
        steps["1. control: UPDATE changes 1 row, then SET NOT NULL"] = p.step(
            1, "UPDATE (1 row), SET NOT NULL", [update, alter], null_row=True
        )
        steps["2. UPDATE changes 0 rows, then SET NOT NULL"] = p.step(
            2, "UPDATE (0 rows), SET NOT NULL", [update, alter]
        )
        steps["3. SELECT ... FETCH FIRST 1 ROW ONLY, then SET NOT NULL"] = p.step(
            3, "SELECT, SET NOT NULL", [select, alter]
        )
        steps["4. LOCK TABLE EXCLUSIVE, SELECT, then SET NOT NULL"] = p.step(
            4,
            "LOCK TABLE, SELECT, SET NOT NULL",
            [f"LOCK TABLE {table} IN EXCLUSIVE MODE", select, alter],
        )
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        if p.exists():
            p.run(f"drop {T}", f"DROP TABLE {table} RESTRICT")
        p.run("discard the QAQQINI copy", inquiry.DISCARD_SQL)
        left = run_query(conn, f"{T} left", PROBE_OBJECTS, (library, T))
        print_query(left)
        if not left["ok"] or left["rows"]:
            print(f"\nWARNING: {T} may be left in {library}: {left}", file=sys.stderr)
    print("\nSummary")
    for label, record in steps.items():
        last = record["statements"][-1]
        outcome = "ok" if last["ok"] else last["message"][:60]
        print(f"  {label[:58]:<58} SET NOT NULL: {outcome}")
    return {"steps": steps, "left": left.get("rows"), "statements": p.steps}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, change and drop the table")
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
        print(f"\nresult saved to {write_result('lib_pending_change', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
