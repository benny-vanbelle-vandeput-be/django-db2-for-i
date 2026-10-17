"""Write probe 07: savepoint syntax and semantics, as Django's atomic() uses them.

THIS CHANGES THE IBM i (one table in the default library, dropped at the
end). Not part of probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_savepoints              # dry run: checks only
    nox -s probe_savepoints -- --execute

Question: can ``uses_savepoints`` (and ``can_release_savepoints``) be
enabled? Django's nested atomic() runs, on the backend's settings (CMT=1,
autocommit off):

    SAVEPOINT "<sid>"          on entry (sid like s140234567890_x1)
    RELEASE SAVEPOINT "<sid>"  on success
    ROLLBACK TO SAVEPOINT "<sid>", then RELEASE SAVEPOINT "<sid>"  on error

Steps: accepted syntax variants; rollback to and release; nesting; a failed
statement inside a savepoint; reusing a name; an open cursor across a
rollback to savepoint; savepoints after COMMIT and in autocommit mode.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from _common import (
    ProbeError,
    Settings,
    connect,
    print_query,
    run_query,
    run_statement,
    run_values,
    write_result,
)

TABLE = "DJSVPT"
# A savepoint name as Django builds it: f"s{thread ident}_x{counter}", quoted.
DJANGO_SID = '"s140234567890123_x1"'


def checks(conn, library: str) -> None:
    journal = run_query(
        conn,
        f"{library}: QSQJRN journal",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN', 'QSQJRN')) X",
        (library,),
    )
    existing = run_query(
        conn,
        f"{library}: probe table exists",
        "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE')) X WHERE OBJNAME = ?",
        (library, TABLE),
    )
    for result in (journal, existing):
        print_query(result)
    if not journal["ok"] or not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not journal["rows"]:
        raise ProbeError("check", f"{library} has no QSQJRN journal; run setup_journal first")
    if existing["rows"]:
        raise ProbeError("check", f"{TABLE} already exists in {library}; nothing was changed")


def run(conn, library: str) -> dict[str, Any]:
    table = f"{library}.{TABLE}"
    steps: list[dict[str, Any]] = []
    created = False

    def stmt(label: str, sql: str) -> bool:
        result = run_statement(conn, label, sql)
        steps.append(result)
        return result["ok"]

    def rows(label: str) -> list[int]:
        result = run_values(conn, label, f"SELECT ID FROM {table} ORDER BY ID")
        steps.append(result)
        return [int(row["ID"]["repr"]) for row in result.get("rows", [])]

    try:
        if not stmt("create table", f"CREATE TABLE {table} (ID INTEGER NOT NULL PRIMARY KEY)"):
            raise ProbeError("refused", "CREATE TABLE failed; nothing else was run")
        created = True
        conn.autocommit = False

        print("\n======== 1. Syntax ========")
        stmt(
            "Django name + ON ROLLBACK RETAIN CURSORS",
            f"SAVEPOINT {DJANGO_SID} ON ROLLBACK RETAIN CURSORS",
        )
        stmt("release Django name", f"RELEASE SAVEPOINT {DJANGO_SID}")
        stmt("without ON ROLLBACK clause", "SAVEPOINT S_PLAIN")
        stmt("release (no TO)", "RELEASE SAVEPOINT S_PLAIN")
        stmt("RELEASE TO SAVEPOINT", "SAVEPOINT S_TO ON ROLLBACK RETAIN CURSORS")
        stmt("RELEASE TO SAVEPOINT form", "RELEASE TO SAVEPOINT S_TO")
        stmt("UNIQUE", "SAVEPOINT S_UNIQUE UNIQUE ON ROLLBACK RETAIN CURSORS")
        stmt("ON ROLLBACK RETAIN LOCKS", "SAVEPOINT S_LOCKS ON ROLLBACK RETAIN LOCKS")
        stmt("long quoted name (40 chars)", f'SAVEPOINT "{"s" * 40}" ON ROLLBACK RETAIN CURSORS')
        conn.rollback()

        print("\n======== 2. Rollback to, then release (Django's error path) ========")
        stmt("insert 1", f"INSERT INTO {table} VALUES (1)")
        stmt("savepoint A", "SAVEPOINT A ON ROLLBACK RETAIN CURSORS")
        stmt("insert 2", f"INSERT INTO {table} VALUES (2)")
        stmt("rollback to A", "ROLLBACK TO SAVEPOINT A")
        after_rollback_to = rows("rows after rollback to A (expect [1])")
        stmt("rollback to A again (savepoint still exists?)", "ROLLBACK TO SAVEPOINT A")
        release_after_rollback = stmt("release A after rollback to", "RELEASE SAVEPOINT A")
        stmt("rollback to released A (expect error)", "ROLLBACK TO SAVEPOINT A")

        print("\n======== 3. Release (Django's success path) ========")
        stmt("savepoint B", "SAVEPOINT B ON ROLLBACK RETAIN CURSORS")
        stmt("insert 3", f"INSERT INTO {table} VALUES (3)")
        release_ok = stmt("release B", "RELEASE SAVEPOINT B")
        after_release = rows("rows after release B (expect [1, 3])")

        print("\n======== 4. Nesting ========")
        stmt("savepoint C", "SAVEPOINT C ON ROLLBACK RETAIN CURSORS")
        stmt("insert 4", f"INSERT INTO {table} VALUES (4)")
        stmt("savepoint D (inside C)", "SAVEPOINT D ON ROLLBACK RETAIN CURSORS")
        stmt("insert 5", f"INSERT INTO {table} VALUES (5)")
        stmt("release D", "RELEASE SAVEPOINT D")
        stmt("rollback to C", "ROLLBACK TO SAVEPOINT C")
        after_nested = rows("rows after rollback to C (expect [1, 3])")
        stmt("savepoint E", "SAVEPOINT E ON ROLLBACK RETAIN CURSORS")
        stmt("savepoint F (inside E)", "SAVEPOINT F ON ROLLBACK RETAIN CURSORS")
        stmt("rollback to E", "ROLLBACK TO SAVEPOINT E")
        stmt("rollback to F after rollback to E (expect error)", "ROLLBACK TO SAVEPOINT F")
        stmt("release C (outer, still active?)", "RELEASE SAVEPOINT C")

        print("\n======== 5. Failed statement inside a savepoint ========")
        stmt("savepoint G", "SAVEPOINT G ON ROLLBACK RETAIN CURSORS")
        stmt("duplicate key 1 (expect SQL0803)", f"INSERT INTO {table} VALUES (1)")
        stmt("rollback to G after the error", "ROLLBACK TO SAVEPOINT G")
        stmt("release G", "RELEASE SAVEPOINT G")
        stmt("insert 6 after recovery", f"INSERT INTO {table} VALUES (6)")
        after_error = rows("rows after recovery (expect [1, 3, 6])")

        print("\n======== 6. Reusing a name ========")
        stmt("savepoint H", "SAVEPOINT H ON ROLLBACK RETAIN CURSORS")
        stmt("insert 7", f"INSERT INTO {table} VALUES (7)")
        stmt("savepoint H again (no UNIQUE)", "SAVEPOINT H ON ROLLBACK RETAIN CURSORS")
        stmt("insert 8", f"INSERT INTO {table} VALUES (8)")
        stmt("rollback to H", "ROLLBACK TO SAVEPOINT H")
        after_reuse = rows("rows after rollback to the second H (expect [1, 3, 6, 7])")
        stmt("release H", "RELEASE SAVEPOINT H")

        print("\n======== 7. Open cursor across rollback to savepoint ========")
        open_cursor: dict[str, Any] = {"label": "open cursor across rollback to savepoint"}
        reader = conn.cursor()
        try:
            reader.execute(f"SELECT ID FROM {table} ORDER BY ID")
            first = reader.fetchone()
            stmt("savepoint I", "SAVEPOINT I ON ROLLBACK RETAIN CURSORS")
            stmt("rollback to I", "ROLLBACK TO SAVEPOINT I")
            rest = reader.fetchall()
            open_cursor.update(ok=True, first=repr(first), rest=repr(rest))
        except Exception as exc:  # recorded, not raised
            open_cursor.update(ok=False, message=str(exc))
        finally:
            reader.close()
        print(f"\n# {open_cursor}")
        steps.append(open_cursor)

        print("\n======== 8. After COMMIT, and in autocommit mode ========")
        stmt("savepoint J", "SAVEPOINT J ON ROLLBACK RETAIN CURSORS")
        conn.commit()
        stmt("rollback to J after COMMIT (expect error)", "ROLLBACK TO SAVEPOINT J")
        conn.rollback()
        conn.autocommit = True
        stmt("savepoint in autocommit mode", "SAVEPOINT K ON ROLLBACK RETAIN CURSORS")
        stmt("release in autocommit mode", "RELEASE SAVEPOINT K")
        final_rows = rows("rows after COMMIT (expect [1, 3, 6, 7])")
    finally:
        conn.autocommit = True
        if created and not stmt("drop table", f"DROP TABLE {table}"):
            print(f"\nWARNING: {table} was NOT dropped; remove it manually.", file=sys.stderr)

    print("\nSummary")
    for result in steps:
        state = "ok" if result["ok"] else f"{result.get('sqlstate', '')} {result['message'][:100]}"
        print(f"  {result['label'][:60]:<60} {state}")
    return {
        "steps": steps,
        "after_rollback_to": after_rollback_to,
        "release_after_rollback_to": release_after_rollback,
        "release": release_ok,
        "after_release": after_release,
        "after_nested": after_nested,
        "after_error": after_error,
        "after_reuse": after_reuse,
        "final_rows": final_rows,
    }


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
        conn = connect(settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1"}, autocommit=True)
        checks(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        result = run(conn, library)
        print(f"\nresult saved to {write_result('w07_savepoints', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
