"""Create a QSQJRN journal in a test library so commitment control works.

THIS CHANGES THE IBM i. It is not a probe and is not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    # dry run: checks and prints the CL commands
    bin/probe --approved <link> lib_setup_journal
    # runs them
    bin/probe --approved <link> lib_setup_journal -- --execute
    # target DB2I_OTHER_LIBRARY instead
    bin/probe --approved <link> lib_setup_journal -- --library other
    # dry run of the removal
    bin/probe --approved <link> lib_setup_journal -- --undo
    # removes journal and receivers
    bin/probe --approved <link> lib_setup_journal -- --undo --execute

Setup, for one library <LIB> (DB2I_DEFAULT_LIBRARY by default):
1. Read-only checks: <LIB> is owned by the current user and has no QSQJRN
   journal or QSQJRN0001 receiver yet.
2. CRTJRNRCV + CRTJRN via QSYS2.QCMDEXC. QSQJRN / QSQJRN0001 are the names
   CREATE SCHEMA uses, so SQL tables created in <LIB> afterwards are journaled
   to QSQJRN automatically.
3. Read-only verification of the journal and the receiver (incl. THRESHOLD).
4. Creates a one-column check table, verifies it is journaled to QSQJRN and
   drops it again.

Receivers are system-managed and deleted when detached (MNGRCV(*SYSTEM)
DLTRCV(*YES)), so storage stays bounded on a shared system.

Undo: DLTJRN, then DLTJRNRCV for every QSQJRN* receiver in <LIB>. DLTJRN fails
while objects are still journaled to QSQJRN; drop those tables first.

If the system refuses a command (e.g. missing authority), the script reports
the CPF message and stops. There is no fallback.
"""

from __future__ import annotations

import argparse
import re
import sys

from _common import ProbeError, Settings, connect, print_query, run_query

JOURNAL = "QSQJRN"
RECEIVER = "QSQJRN0001"
# Receiver size threshold in KB before the system attaches a new receiver.
RECEIVER_THRESHOLD_KB = 100000
TEXT = "django-db2-for-i test journal"
CHECK_TABLE = "DJJRNCHK"

_SYSTEM_NAME = re.compile(r"^[A-Z#@$][A-Z0-9#@$_]{0,9}$")


def setup_commands(library: str) -> list[str]:
    return [
        f"CRTJRNRCV JRNRCV({library}/{RECEIVER}) THRESHOLD({RECEIVER_THRESHOLD_KB}) TEXT('{TEXT}')",
        f"CRTJRN JRN({library}/{JOURNAL}) JRNRCV({library}/{RECEIVER}) "
        f"MNGRCV(*SYSTEM) DLTRCV(*YES) TEXT('{TEXT}')",
    ]


def undo_commands(library: str, receivers: list[str]) -> list[str]:
    return [f"DLTJRN JRN({library}/{JOURNAL})"] + [
        f"DLTJRNRCV JRNRCV({library}/{receiver}) DLTOPT(*IGNINQMSG)" for receiver in receivers
    ]


def journal_objects(conn, library: str) -> list[dict]:
    result = run_query(
        conn,
        f"{library}: existing journal objects",
        "SELECT OBJNAME, OBJTYPE FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN *JRNRCV')) X",
        (library,),
    )
    print_query(result)
    if not result["ok"]:
        raise ProbeError("check", "journal objects could not be listed; nothing was changed")
    return result["rows"]


def check_owned(conn, library: str) -> None:
    owned = run_query(
        conn,
        f"{library}: owned by current user",
        "SELECT OBJECT_NAME FROM QSYS2.OBJECT_OWNERSHIP "
        "WHERE AUTHORIZATION_NAME = CURRENT USER AND OBJECT_TYPE = '*LIB' AND OBJECT_NAME = ?",
        (library,),
    )
    print_query(owned)
    if not owned["ok"]:
        raise ProbeError("check", "ownership check could not run; nothing was changed")
    if not owned["rows"]:
        raise ProbeError(
            "check", f"{library} is not owned by the current user; nothing was changed"
        )


def _execute(conn, sql: str, params: tuple = ()) -> None:
    """Run one statement; a refusal stops the script with the server's message."""
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
    except pyodbc.Error as exc:
        args = exc.args
        sqlstate = str(args[0]) if len(args) > 1 else ""
        message = str(args[1] if len(args) > 1 else exc)
        raise ProbeError(
            "refused",
            f"the system refused the statement; stopping (no fallback).\n"
            f"  SQLSTATE: {sqlstate or '-'}\n  message: {message}\n"
            "  Statements that completed before this one were not undone.",
        ) from None
    finally:
        cursor.close()


def run_commands(conn, commands: list[str]) -> None:
    for command in commands:
        print(f"\n> {command}")
        _execute(conn, "CALL QSYS2.QCMDEXC(?)", (command,))
        print("  ok")


def verify_journal(conn, library: str) -> None:
    # SELECT *: report every column the release provides.
    print_query(
        run_query(
            conn,
            f"{library}: journal state (QSYS2.JOURNAL_INFO)",
            "SELECT * FROM QSYS2.JOURNAL_INFO WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?",
            (library, JOURNAL),
        )
    )
    print_query(
        run_query(
            conn,
            f"{library}: journal receivers (QSYS2.JOURNAL_RECEIVER_INFO)",
            "SELECT * FROM QSYS2.JOURNAL_RECEIVER_INFO WHERE JOURNAL_RECEIVER_LIBRARY = ?",
            (library,),
        )
    )


def verify_table_journaling(conn, library: str) -> bool | None:
    """Create a check table, report whether it is journaled to QSQJRN, drop it."""
    table = f"{library}.{CHECK_TABLE}"
    print(f"\n> CREATE TABLE {table} (ID INTEGER)")
    _execute(conn, f"CREATE TABLE {table} (ID INTEGER)")
    try:
        result = run_query(
            conn,
            f"{table}: journaling",
            "SELECT OBJNAME, JOURNALED, JOURNAL_NAME, JOURNAL_LIBRARY "
            "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', ?)) X",
            (library, CHECK_TABLE),
        )
        print_query(result)
    finally:
        print(f"\n> DROP TABLE {table}")
        _execute(conn, f"DROP TABLE {table}")
        print("  ok")
    if not result["ok"] or not result["rows"]:
        return None
    row = result["rows"][0]
    return (
        row.get("JOURNALED") == "YES"
        and row.get("JOURNAL_NAME") == JOURNAL
        and row.get("JOURNAL_LIBRARY") == library
    )


def setup(conn, library: str, execute: bool) -> None:
    print("CL commands:")
    for command in setup_commands(library):
        print(f"  {command}")
    check_owned(conn, library)
    names = [row["OBJNAME"] for row in journal_objects(conn, library)]
    clash = [name for name in names if name in (JOURNAL, RECEIVER)]
    if clash:
        raise ProbeError(
            "check", f"{library} already contains {', '.join(clash)}; nothing was changed"
        )
    if not execute:
        print("\nDry run: nothing was changed. Re-run with --execute to apply.")
        return
    run_commands(conn, setup_commands(library))
    verify_journal(conn, library)
    journaled = verify_table_journaling(conn, library)
    state = {
        True: f"new SQL tables in {library} are journaled to {JOURNAL}",
        False: f"new SQL tables in {library} are NOT journaled to {JOURNAL}",
        None: "table journaling could not be verified",
    }
    print(f"\nResult: {state[journaled]}")
    if not journaled:
        raise ProbeError("verify", state[journaled])


def undo(conn, library: str, execute: bool) -> None:
    check_owned(conn, library)
    objects = journal_objects(conn, library)
    if not any(row["OBJNAME"] == JOURNAL and row["OBJTYPE"] == "*JRN" for row in objects):
        raise ProbeError("check", f"{library} has no {JOURNAL} journal; nothing was changed")
    receivers = [
        row["OBJNAME"]
        for row in objects
        if row["OBJTYPE"] == "*JRNRCV" and row["OBJNAME"].startswith(JOURNAL)
    ]
    commands = undo_commands(library, receivers)
    print("\nCL commands:")
    for command in commands:
        print(f"  {command}")
    if not execute:
        print("\nDry run: nothing was changed. Re-run with --undo --execute to apply.")
        return
    run_commands(conn, commands)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library", choices=["default", "other"], default="default")
    parser.add_argument("--undo", action="store_true", help="remove the journal and receivers")
    parser.add_argument("--execute", action="store_true", help="run the CL commands")
    args = parser.parse_args(argv)

    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library if args.library == "default" else settings.other_library
        variable = f"DB2I_{args.library.upper()}_LIBRARY"
        if not library:
            raise ProbeError("config", f"{variable} is not set", 1)
        if not _SYSTEM_NAME.match(library):
            raise ProbeError("config", f"{variable} is not a valid system library name", 1)
        print(f"Target library ({variable}): {library}")

        conn = connect(settings)
        (undo if args.undo else setup)(conn, library, args.execute)
    except ProbeError as exc:
        print(f"\nSETUP FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
