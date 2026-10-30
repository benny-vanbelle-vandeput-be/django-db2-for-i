"""How unique constraints treat NULLs, and how the catalog shows partial and
expression indexes (phase 5, steps C and D; issue #213).

THIS CHANGES THE IBM i: one table, DJDB2I_P5UNQ, in the journaled default
library, recorded on the cleanup list (tests/table_registry.py) before its
CREATE TABLE and dropped at the end, also after a failure. On it, one at a
time, each dropped before the next: the unique constraints (A) and (A, B), a
partial index, an expression index, a unique partial index, a UNIQUE WHERE
NOT NULL index and an index with both an expression and a condition.
Approved by the maintainer on issue #213 (comment 6518630670) with one
condition: the inserts of each constraint or index run in their own
transaction, ended with ROLLBACK before the next DROP / ADD / CREATE INDEX,
so the probe measures NULL behaviour, not the pending-row-change limitation
of #173 (SQL0910). Run only through the PUB400 lock. Not part of
probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_unique_catalog              # dry run: checks only
    bin/probe --approved <link> lib_unique_catalog -- --execute

Per case: the DDL in autocommit; the catalog rows of this table only
(QSYS2.SYSCST, SYSKEYCST, SYSINDEXES, SYSKEYS); for a unique case the inserts
(one NULL, a second NULL; (1, NULL) twice; (NULL, NULL) twice; a real
duplicate; for a condition, duplicates inside and outside it) with autocommit
off, each recorded as ok or its SQLCODE, then ROLLBACK; then the DROP. One
connection with the backend's attributes (CMT=1, TRUEAUTOCOMMIT=1), no
retries.
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

T = "DJDB2I_P5UNQ"
BODY = "ID INTEGER NOT NULL PRIMARY KEY, A INTEGER, B INTEGER, C NVARCHAR(20)"
PROBE_OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"

# (ID, A, B, C) rows inserted one by one for a unique case, in this order.
NULL_ROWS = [
    ("one NULL in A", (1, None, None, "x")),
    ("a second NULL in A", (2, None, None, "x")),
    ("(1, NULL)", (3, 1, None, "x")),
    ("(1, NULL) again", (4, 1, None, "x")),
    ("(NULL, NULL) again", (5, None, None, "x")),
    ("(2, 2)", (6, 2, 2, "x")),
    ("(2, 2) again: a real duplicate", (7, 2, 2, "x")),
]
# For an index WHERE B > 0: duplicates of A inside and outside the condition.
CONDITION_ROWS = [
    ("A=5, B=1 (inside)", (11, 5, 1, "x")),
    ("A=5, B=2 (inside): duplicate A", (12, 5, 2, "x")),
    ("A=6, B=0 (outside)", (13, 6, 0, "x")),
    ("A=6, B=0 (outside) again", (14, 6, 0, "x")),
    ("A=7, B=NULL (outside)", (15, 7, None, "x")),
    ("A=7, B=NULL (outside) again", (16, 7, None, "x")),
]


def sqlcode(message: str) -> str:
    """The SQLCODE the driver puts in its message, e.g. '(-803)'."""
    match = re.search(r"\((-?\d+)\)", message)
    return match.group(1) if match else "?"


class Probe:
    def __init__(self, conn, library: str):
        self.conn = conn
        self.library = library
        self.table = f"{library}.{T}"
        self.registry = table_registry.list_path()
        self.steps: list[dict[str, Any]] = []

    def run(self, label: str, sql: str, params: tuple = ()) -> dict[str, Any]:
        result = run_statement(self.conn, label, sql, params)
        self.steps.append(result)
        return result

    def rows(self, label: str, sql: str) -> list[dict[str, Any]] | str:
        result = run_query(self.conn, label, sql, (self.library, T))
        print_query(result)
        if not result["ok"]:
            return f"error {result.get('sqlstate')} {result.get('message', '')[:120]}"
        return result["rows"]

    def exists(self) -> bool:
        result = run_query(self.conn, f"{T} exists", PROBE_OBJECTS, (self.library, T))
        return bool(result["ok"] and result["rows"])

    def create(self) -> None:
        sql = f"CREATE TABLE {self.table} ({BODY})"
        entry = table_registry.parse(sql, self.library)
        assert entry is not None and entry.name == T
        table_registry.record(self.registry, entry)
        if not self.run(f"create {T}", sql)["ok"]:
            raise ProbeError("refused", f"create {T} failed; nothing else was run")

    def catalog(self) -> dict[str, Any]:
        """The catalog rows of this table only."""
        return {
            "SYSCST": self.rows(
                "SYSCST",
                "SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE, CONSTRAINT_KEYS "
                "FROM QSYS2.SYSCST WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
                "ORDER BY CONSTRAINT_NAME",
            ),
            "SYSKEYCST": self.rows(
                "SYSKEYCST",
                "SELECT CONSTRAINT_NAME, COLUMN_NAME, ORDINAL_POSITION "
                "FROM QSYS2.SYSKEYCST WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? "
                "ORDER BY CONSTRAINT_NAME, ORDINAL_POSITION",
            ),
            "SYSINDEXES": self.rows(
                "SYSINDEXES",
                "SELECT INDEX_NAME, IS_UNIQUE, COLUMN_COUNT, INDEX_HAS_SEARCH_CONDITION, "
                "SEARCH_CONDITION FROM QSYS2.SYSINDEXES "
                "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY INDEX_NAME",
            ),
            "SYSKEYS": self.rows(
                "SYSKEYS",
                "SELECT K.INDEX_NAME, K.COLUMN_NAME, K.ORDINAL_POSITION, K.ORDERING, "
                "K.COLUMN_IS_EXPRESSION, K.KEY_EXPRESSION "
                "FROM QSYS2.SYSKEYS K JOIN QSYS2.SYSINDEXES I "
                "ON K.INDEX_SCHEMA = I.INDEX_SCHEMA AND K.INDEX_NAME = I.INDEX_NAME "
                "WHERE I.TABLE_SCHEMA = ? AND I.TABLE_NAME = ? "
                "ORDER BY K.INDEX_NAME, K.ORDINAL_POSITION",
            ),
        }

    def inserts(self, rows: list[tuple[str, tuple]]) -> dict[str, Any]:
        """The inserts of one case in their own transaction, ended with ROLLBACK
        before the next DDL (#213's condition)."""
        self.conn.autocommit = False
        outcomes: dict[str, str] = {}
        try:
            for label, values in rows:
                result = self.run(
                    label, f"INSERT INTO {self.table} (ID, A, B, C) VALUES (?, ?, ?, ?)", values
                )
                outcomes[label] = "ok" if result["ok"] else sqlcode(result.get("message", ""))
        finally:
            rollback = "ok"
            try:
                self.conn.rollback()
            except Exception as exc:  # recorded, the probe goes on
                rollback = f"error {exc!s:.120}"
            self.conn.autocommit = True
        return {"inserts": outcomes, "rollback": rollback}

    def case(
        self, number: int, label: str, create: str, drop: str, rows: list | None
    ) -> dict[str, Any]:
        print(f"\n======== {number}. {label} ========")
        made = self.run(label, create)
        record: dict[str, Any] = {"ddl": create, "ok": made["ok"]}
        if not made["ok"]:
            record["sqlstate"] = made.get("sqlstate", "")
            record["message"] = made.get("message", "")[:200]
            return record
        record["catalog"] = self.catalog()
        if rows is not None:
            record.update(self.inserts(rows))
        dropped = self.run(f"drop: {label}", drop)
        record["dropped"] = dropped["ok"] or dropped.get("message", "")[:120]
        print(f"  {record.get('inserts', '')}")
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


def run(conn, library: str) -> dict[str, Any]:
    p = Probe(conn, library)
    t = p.table
    name = f"{library}.{T}"

    def index(suffix: str) -> str:
        return f"{library}.{T}_{suffix}"

    cases: dict[str, Any] = {}
    try:
        p.create()
        cases["1. UNIQUE constraint (A)"] = p.case(
            1,
            "UNIQUE constraint (A)",
            f"ALTER TABLE {t} ADD CONSTRAINT {T}_UA UNIQUE (A)",
            f"ALTER TABLE {t} DROP CONSTRAINT {T}_UA",
            NULL_ROWS,
        )
        cases["2. UNIQUE constraint (A, B)"] = p.case(
            2,
            "UNIQUE constraint (A, B)",
            f"ALTER TABLE {t} ADD CONSTRAINT {T}_UAB UNIQUE (A, B)",
            f"ALTER TABLE {t} DROP CONSTRAINT {T}_UAB",
            NULL_ROWS,
        )
        cases["3. partial index (A) WHERE B > 0"] = p.case(
            3,
            "partial index (A) WHERE B > 0",
            f"CREATE INDEX {index('P')} ON {name} (A) WHERE B > 0",
            f"DROP INDEX {index('P')}",
            None,
        )
        cases["4. expression index (UPPER(C))"] = p.case(
            4,
            "expression index (UPPER(C))",
            f"CREATE INDEX {index('E')} ON {name} (UPPER(C))",
            f"DROP INDEX {index('E')}",
            None,
        )
        cases["5. unique partial index (A) WHERE B > 0"] = p.case(
            5,
            "unique partial index (A) WHERE B > 0",
            f"CREATE UNIQUE INDEX {index('UP')} ON {name} (A) WHERE B > 0",
            f"DROP INDEX {index('UP')}",
            NULL_ROWS + CONDITION_ROWS,
        )
        cases["6. UNIQUE WHERE NOT NULL index (A)"] = p.case(
            6,
            "UNIQUE WHERE NOT NULL index (A)",
            f"CREATE UNIQUE WHERE NOT NULL INDEX {index('UN')} ON {name} (A)",
            f"DROP INDEX {index('UN')}",
            NULL_ROWS,
        )
        cases["7. index (A, UPPER(C)) WHERE B > 0"] = p.case(
            7,
            "index (A, UPPER(C)) WHERE B > 0",
            f"CREATE INDEX {index('EP')} ON {name} (A, UPPER(C)) WHERE B > 0",
            f"DROP INDEX {index('EP')}",
            None,
        )
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        if p.exists():
            p.run(f"drop {T}", f"DROP TABLE {t}")
        left = run_query(conn, f"{T} left", PROBE_OBJECTS, (library, T))
        print_query(left)
        if not left["ok"] or left["rows"]:
            print(f"\nWARNING: {T} may be left in {library}: {left}", file=sys.stderr)
    print("\nSummary")
    for label, record in cases.items():
        print(f"  {label}: {record.get('inserts') or ('ok' if record['ok'] else record)}")
    return {"cases": cases, "left": left.get("rows"), "statements": p.steps}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the table")
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
        print(f"\nresult saved to {write_result('lib_unique_catalog', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
