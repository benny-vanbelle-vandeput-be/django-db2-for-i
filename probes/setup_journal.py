"""Create a QSQJRN journal in a test library so commitment control works.

THIS CHANGES THE IBM i. It is not a probe and is not part of probes/run.py.

Usage (inside the "tests" container):
    nox -s setup_journal                      # dry run: checks and prints the CL commands
    nox -s setup_journal -- --execute         # runs them
    nox -s setup_journal -- --library other   # target DB2I_OTHER_LIBRARY instead

What it does, for one library <LIB> (DB2I_DEFAULT_LIBRARY by default):
1. Read-only checks: <LIB> is owned by the current user and has no QSQJRN
   journal or QSQJRN0001 receiver yet.
2. CRTJRNRCV + CRTJRN via QSYS2.QCMDEXC. QSQJRN / QSQJRN0001 are the names
   CREATE SCHEMA uses, so SQL tables created in <LIB> afterwards are journaled
   to QSQJRN automatically.
3. Read-only verification via QSYS2.JOURNAL_INFO.

Receivers are system-managed and deleted when detached (MNGRCV(*SYSTEM)
DLTRCV(*YES)), so storage stays bounded on a shared system.

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

_SYSTEM_NAME = re.compile(r"^[A-Z#@$][A-Z0-9#@$_]{0,9}$")


def cl_commands(library: str) -> list[str]:
    return [
        f"CRTJRNRCV JRNRCV({library}/{RECEIVER}) THRESHOLD({RECEIVER_THRESHOLD_KB}) TEXT('{TEXT}')",
        f"CRTJRN JRN({library}/{JOURNAL}) JRNRCV({library}/{RECEIVER}) "
        f"MNGRCV(*SYSTEM) DLTRCV(*YES) TEXT('{TEXT}')",
    ]


def check(conn, library: str) -> None:
    owned = run_query(
        conn,
        f"{library}: owned by current user",
        "SELECT OBJECT_NAME FROM QSYS2.OBJECT_OWNERSHIP "
        "WHERE AUTHORIZATION_NAME = CURRENT USER AND OBJECT_TYPE = '*LIB' AND OBJECT_NAME = ?",
        (library,),
    )
    existing = run_query(
        conn,
        f"{library}: existing journal objects",
        "SELECT OBJNAME, OBJTYPE FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*JRN *JRNRCV')) X",
        (library,),
    )
    print_query(owned)
    print_query(existing)
    if not owned["ok"] or not existing["ok"]:
        raise ProbeError("check", "pre-checks could not run; nothing was changed")
    if not owned["rows"]:
        raise ProbeError(
            "check", f"{library} is not owned by the current user; nothing was changed"
        )
    names = [row["OBJNAME"] for row in existing["rows"]]
    clash = [name for name in names if name in (JOURNAL, RECEIVER)]
    if clash:
        raise ProbeError(
            "check", f"{library} already contains {', '.join(clash)}; nothing was changed"
        )


def execute(conn, library: str) -> None:
    import pyodbc

    for command in cl_commands(library):
        print(f"\n> {command}")
        cursor = conn.cursor()
        try:
            cursor.execute("CALL QSYS2.QCMDEXC(?)", (command,))
        except pyodbc.Error as exc:
            args = exc.args
            sqlstate = str(args[0]) if len(args) > 1 else ""
            message = str(args[1] if len(args) > 1 else exc)
            raise ProbeError(
                "refused",
                f"the system refused the command; stopping (no fallback).\n"
                f"  SQLSTATE: {sqlstate or '-'}\n  message: {message}\n"
                "  Commands that completed before this one were not undone.",
            ) from None
        finally:
            cursor.close()
        print("  ok")


def verify(conn, library: str) -> None:
    print_query(
        run_query(
            conn,
            f"{library}: journal state",
            "SELECT JOURNAL_NAME, JOURNAL_LIBRARY, ATTACHED_JOURNAL_RECEIVER_NAME, "
            "RECEIVER_MANAGEMENT, DELETE_RECEIVER_OPTION, JOURNAL_STATE "
            "FROM QSYS2.JOURNAL_INFO WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?",
            (library, JOURNAL),
        )
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--library", choices=["default", "other"], default="default")
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
        print("CL commands:")
        for command in cl_commands(library):
            print(f"  {command}")

        conn = connect(settings)
        check(conn, library)
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        execute(conn, library)
        verify(conn, library)
    except ProbeError as exc:
        print(f"\nSETUP FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
