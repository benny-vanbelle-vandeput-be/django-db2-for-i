"""What LOCK TABLE leaves other jobs (issue #162).

THIS CHANGES THE IBM i: one table, DJDB2I_LOCKPROBE (ID INTEGER, V INTEGER, 2 rows),
in the journaled default library, recorded on the cleanup list
(tests/table_registry.py) before its CREATE TABLE, its record wait time set with
CHGPF WAITRCD(2), and dropped at the end, also after a failure.

Approved by the maintainer on issue #162 (comment 6801604658), as described there.
Two connections at the same time (jobs A and B, the backend's attributes, *CS):
A locks the table IN EXCLUSIVE MODE, then IN SHARE MODE; while it holds the lock, B
runs each statement once (result and time), rolled back after each; then A rolls
back and B runs a control SELECT and INSERT. Each connection is opened once, no
retries. Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_lock_table              # dry run: checks only
    bin/probe --approved <link> lib_lock_table -- --execute
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import _twojobs as two
from _common import ProbeError, Settings, write_result

TABLE = "DJDB2I_LOCKPROBE"


def b_statements(t: str) -> tuple[tuple[str, str], ...]:
    return (
        ("SELECT (*CS)", f"SELECT ID, V FROM {t} ORDER BY ID"),
        ("SELECT WITH UR", f"SELECT ID, V FROM {t} ORDER BY ID WITH UR"),
        ("SELECT WITH NC", f"SELECT ID, V FROM {t} ORDER BY ID WITH NC"),
        ("INSERT", f"INSERT INTO {t} VALUES (3, 3)"),
        ("UPDATE", f"UPDATE {t} SET V = V + 1 WHERE ID = 1"),
        ("DELETE", f"DELETE FROM {t} WHERE ID = 2"),
        ("ALTER TABLE ADD COLUMN", f"ALTER TABLE {t} ADD COLUMN W INTEGER"),
        ("LOCK TABLE IN SHARE MODE", f"LOCK TABLE {t} IN SHARE MODE"),
    )


def series(job_a, job_b, t: str, mode: str) -> dict[str, Any]:
    print(f"\n======== A: LOCK TABLE IN {mode} MODE ========")
    record: dict[str, Any] = {
        "A lock": two.timed(job_a, f"A lock {mode}", f"LOCK TABLE {t} IN {mode} MODE")
    }
    if record["A lock"]["ok"]:
        for label, sql in b_statements(t):
            fetch = sql.startswith("SELECT")
            record[f"B {label}"] = two.timed(job_b, f"B {label}", sql, fetch=fetch)
            two.end(job_b)
    record["A rollback"] = two.end(job_a)
    record["B control SELECT"] = two.timed(
        job_b, "B control SELECT", f"SELECT ID, V FROM {t} ORDER BY ID", fetch=True
    )
    record["B control INSERT"] = two.timed(
        job_b, "B control INSERT", f"INSERT INTO {t} VALUES (4, 4)"
    )
    two.end(job_b)
    return record


def run(job_a, job_b, library: str) -> dict[str, Any]:
    t = f"{library}.{TABLE}"
    rounds: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    try:
        two.create(job_a, library, TABLE, "ID INTEGER, V INTEGER", "(1, 1), (2, 2)")
        for mode in ("EXCLUSIVE", "SHARE"):
            rounds[mode] = series(job_a, job_b, t, mode)
    finally:
        two.end(job_b)
        cleanup = two.drop(job_a, library, (TABLE,))
    print("\nSummary")
    for mode, record in rounds.items():
        for label, result in record.items():
            if isinstance(result, dict):
                print(f"  {mode}: {label}: {two.outcome(result)}")
    return {"rounds": rounds, "cleanup": cleanup}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the table")
    args = parser.parse_args(argv)
    jobs: list = []
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        jobs.append(two.open_job(settings, library))
        two.checks(jobs[0], library, (TABLE,))
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        jobs.append(two.open_job(settings, library))
        result = run(jobs[0], jobs[1], library)
        print(f"\nresult saved to {write_result('lib_lock_table', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        for conn in reversed(jobs):
            two.end(conn)
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
