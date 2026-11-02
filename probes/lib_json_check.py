"""A CHECK ... IS JSON on an NCLOB, for phase 6 (the JSONField column; issue #221).

THIS CHANGES THE IBM i: two tables, DJDB2I_P6JSON and DJDB2I_P6JSON2, in the journaled
default library, recorded on the cleanup list (tests/table_registry.py) before their
CREATE TABLE and dropped at the end with RESTRICT, also after a failure.

Approved by the maintainer on issue #221 (comment 6554376430) with two points:

- Django's JSONField stores top-level scalars (1, "x", JSON null). If CHECK (C IS JSON)
  refuses any of them, the probe also tries the explicit variants (IS JSON VALUE, ...), so
  the JSONField PR knows which form accepts all JSON values.
- JSON null (the text 'null') and SQL NULL are separate cases in the result.

Each case's inserts run in their own transaction, ended with ROLLBACK before any further
DDL (the condition from #213). Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_json_check              # dry run: checks only
    bin/probe --approved <link> lib_json_check -- --execute

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

T = "DJDB2I_P6JSON"
T2 = "DJDB2I_P6JSON2"
CHECK = "DJDB2I_P6JSON_CK"
BODY = "ID INTEGER NOT NULL PRIMARY KEY, C NCLOB"
PROBE_OBJECTS = "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X"

# label, the value; every label is its own row, so the result reads per case.
VALUES: tuple[tuple[str, str | None], ...] = (
    ("an object", '{"a": 1}'),
    ("an array", "[1, 2]"),
    ("a number", "1"),
    ("a string", '"x"'),
    ("true", "true"),
    ("false", "false"),
    ("JSON null (the text 'null')", "null"),
    ("SQL NULL", None),
    ("non-ASCII text", '{"a": "téxt \U0001f600"}'),
    ("not JSON", "not json"),
    ("an empty string", ""),
    ("duplicate keys", '{"a": 1, "a": 2}'),
)
SCALARS = {"a number", "a string", "true", "false", "JSON null (the text 'null')"}
VARIANTS = ("IS JSON VALUE", "IS JSON SCALAR", "IS JSON ARRAY", "IS JSON OBJECT")


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

    def rows(self, label: str, sql: str, params: tuple) -> list[dict[str, Any]] | str:
        result = run_query(self.conn, label, sql, params)
        print_query(result)
        if not result["ok"]:
            return f"error {result.get('sqlstate')} {result.get('message', '')[:120]}"
        return result["rows"]

    def exists(self, table: str) -> bool:
        result = run_query(self.conn, f"{table} exists", PROBE_OBJECTS, (self.library, table))
        return bool(result["ok"] and result["rows"])

    def record(self, sql: str, table: str) -> None:
        entry = table_registry.parse(sql, self.library)
        assert entry is not None and entry.name == table
        table_registry.record(self.registry, entry)

    def catalog(self, table: str) -> dict[str, Any]:
        """The catalog rows of this table only."""
        return {
            "SYSCST": self.rows(
                "SYSCST",
                "SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE FROM QSYS2.SYSCST "
                "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY CONSTRAINT_NAME",
                (self.library, table),
            ),
            "SYSCHKCST": self.rows(
                "SYSCHKCST",
                "SELECT K.CONSTRAINT_NAME, K.CHECK_CLAUSE FROM QSYS2.SYSCHKCST K "
                "JOIN QSYS2.SYSCST C ON K.CONSTRAINT_SCHEMA = C.CONSTRAINT_SCHEMA "
                "AND K.CONSTRAINT_NAME = C.CONSTRAINT_NAME "
                "WHERE C.TABLE_SCHEMA = ? AND C.TABLE_NAME = ?",
                (self.library, table),
            ),
        }

    def inserts(self, table: str) -> dict[str, Any]:
        """Every value in one transaction, ended with ROLLBACK before any further DDL. The
        rows are read back, so JSON null and SQL NULL can be told apart."""
        name = f"{self.library}.{table}"
        self.conn.autocommit = False
        outcomes: dict[str, str] = {}
        record: dict[str, Any] = {}
        try:
            for number, (label, value) in enumerate(VALUES, 1):
                result = self.run(
                    label, f"INSERT INTO {name} (ID, C) VALUES (?, ?)", (number, value)
                )
                outcomes[label] = "ok" if result["ok"] else sqlcode(result.get("message", ""))
            record["inserts"] = outcomes
            record["read back"] = self.rows(
                "read back",
                f"SELECT ID, C, CASE WHEN C IS NULL THEN 'SQL NULL' ELSE 'value' END AS KIND "
                f"FROM {name} WHERE ID > ? ORDER BY ID",
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

    def alter_case(self, form: str) -> dict[str, Any]:
        print(f"\n======== CHECK (C {form}) by ALTER TABLE ========")
        name = f"{self.library}.{T}"
        ddl = f"ALTER TABLE {name} ADD CONSTRAINT {CHECK} CHECK (C {form})"
        made = self.run(form, ddl)
        record: dict[str, Any] = {"ddl": ddl, "ok": made["ok"]}
        if not made["ok"]:
            record["sqlstate"] = made.get("sqlstate", "")
            record["message"] = made.get("message", "")[:200]
            return record
        record["catalog"] = self.catalog(T)
        record.update(self.inserts(T))
        dropped = self.run(f"drop {form}", f"ALTER TABLE {name} DROP CONSTRAINT {CHECK}")
        record["dropped"] = dropped["ok"] or dropped.get("message", "")[:120]
        return record

    def create_case(self) -> dict[str, Any]:
        print("\n======== CHECK (C IS JSON) in CREATE TABLE ========")
        sql = (
            f"CREATE TABLE {self.library}.{T2} "
            "(ID INTEGER NOT NULL PRIMARY KEY, C NCLOB CHECK (C IS JSON))"
        )
        self.record(sql, T2)
        made = self.run("create with the check", sql)
        record: dict[str, Any] = {"ddl": sql, "ok": made["ok"]}
        if not made["ok"]:
            record["sqlstate"] = made.get("sqlstate", "")
            record["message"] = made.get("message", "")[:200]
            return record
        record["catalog"] = self.catalog(T2)
        record.update(self.inserts(T2))
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
    for table in (T, T2):
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
        sql = f"CREATE TABLE {library}.{T} ({BODY})"
        p.record(sql, T)
        if not p.run(f"create {T}", sql)["ok"]:
            raise ProbeError("refused", f"create {T} failed; nothing else was run")
        cases["without a check (the control)"] = p.inserts(T)
        base = p.alter_case("IS JSON")
        cases["CHECK (C IS JSON), ALTER TABLE"] = base
        cases["CHECK (C IS JSON), CREATE TABLE"] = p.create_case()
        refused = sorted(
            label
            for label, code in base.get("inserts", {}).items()
            if label in SCALARS and code != "ok"
        )
        # The maintainer's point on #221: only if IS JSON refuses a top-level scalar.
        cases["scalars IS JSON refused"] = refused or (
            "none" if base["ok"] else "the check itself was refused"
        )
        if refused or not base["ok"]:
            for form in VARIANTS:
                cases[f"CHECK (C {form}), ALTER TABLE"] = p.alter_case(form)
    finally:
        with contextlib.suppress(Exception):  # cleanup goes on
            conn.rollback()
        conn.autocommit = True
        for table in (T2, T):
            if p.exists(table):
                dropped = p.run(f"drop {table}", f"DROP TABLE {library}.{table} RESTRICT")
                cleanup[table] = dropped["ok"] or dropped.get("message", "")[:160]
        left = [table for table in (T, T2) if p.exists(table)]
        if left:
            print(f"\nWARNING: {left} may be left in {library}", file=sys.stderr)
    print("\nSummary")
    for label, record in cases.items():
        print(f"  {label}: {record.get('inserts', record) if isinstance(record, dict) else record}")
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
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        conn = connect(
            settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1", "DBQ": library}, autocommit=True
        )
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('lib_json_check', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
