"""What the row locks of select_for_update() lock (issue #237).

THIS CHANGES THE IBM i: two tables, DJDB2I_SFUPARENT (ID, V; 3 rows) and
DJDB2I_SFUCHILD (ID, PARENT_ID, V; 3 rows), in the journaled default library,
recorded on the cleanup list (tests/table_registry.py) before their CREATE TABLE,
their record wait time set with CHGPF WAITRCD(2), and dropped at the end, also
after a failure.

Approved by the maintainer on issue #237 (comment 6801572800), as described there,
plus: SKIP LOCKED DATA and FOR UPDATE OF <columns> are tested too, so the result
decides has_select_for_update_skip_locked and has_select_for_update_of as well.

Two connections at the same time (jobs A and B, the backend's attributes, *CS,
autocommit off). Per round, A locks with one form, fetching all rows and closing
the cursor as Django does; B runs each statement once (result, rows, time), rolled
back after each; then A rolls back and B runs a control SELECT and UPDATE. Then
SET CURRENT LOCK TIMEOUT (the candidate for nowait=True), and B waiting while A
commits or rolls back after 0.5 s. Each connection is opened once, no retries.
Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_select_for_update              # dry run: checks only
    bin/probe --approved <link> lib_select_for_update -- --execute
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import _twojobs as two
from _common import ProbeError, Settings, write_result

PARENT = "DJDB2I_SFUPARENT"
CHILD = "DJDB2I_SFUCHILD"
KEEP = "WITH RS USE AND KEEP EXCLUSIVE LOCKS"


def a_forms(p: str, c: str) -> tuple[tuple[str, str], ...]:
    """How A locks; each fetches all rows and closes the cursor, as Django does."""
    return (
        ("FOR UPDATE", f"SELECT ID, V FROM {p} WHERE ID = 1 FOR UPDATE"),
        ("FOR UPDATE WITH RS", f"SELECT ID, V FROM {p} WHERE ID = 1 FOR UPDATE WITH RS"),
        ("USE AND KEEP", f"SELECT ID, V FROM {p} WHERE ID = 1 {KEEP}"),
        ("FOR UPDATE OF V", f"SELECT ID, V FROM {p} WHERE ID = 1 FOR UPDATE OF V"),
        ("FOR UPDATE OF V WITH RS", f"SELECT ID, V FROM {p} WHERE ID = 1 FOR UPDATE OF V WITH RS"),
        (
            "a slice, USE AND KEEP",
            f"SELECT ID, V FROM {p} ORDER BY ID FETCH FIRST 1 ROWS ONLY {KEEP}",
        ),
        (
            "a join, USE AND KEEP",
            f"SELECT P.ID, C.ID FROM {p} P JOIN {c} C ON C.PARENT_ID = P.ID WHERE P.ID = 1 {KEEP}",
        ),
    )


def b_statements(p: str, c: str) -> tuple[tuple[str, str], ...]:
    return (
        ("SELECT row 1 (*CS)", f"SELECT ID, V FROM {p} WHERE ID = 1"),
        ("SELECT row 1 WITH UR", f"SELECT ID, V FROM {p} WHERE ID = 1 WITH UR"),
        ("SELECT row 1 WITH NC", f"SELECT ID, V FROM {p} WHERE ID = 1 WITH NC"),
        ("UPDATE row 1", f"UPDATE {p} SET V = V + 1 WHERE ID = 1"),
        ("UPDATE row 2", f"UPDATE {p} SET V = V + 1 WHERE ID = 2"),
        ("UPDATE child of row 1", f"UPDATE {c} SET V = V + 1 WHERE PARENT_ID = 1"),
        (
            "FOR UPDATE SKIP LOCKED DATA",
            f"SELECT ID FROM {p} ORDER BY ID FOR UPDATE SKIP LOCKED DATA",
        ),
        (
            "FOR UPDATE OF V SKIP LOCKED DATA",
            f"SELECT ID, V FROM {p} ORDER BY ID FOR UPDATE OF V SKIP LOCKED DATA",
        ),
        ("WITH CS SKIP LOCKED DATA", f"SELECT ID FROM {p} ORDER BY ID WITH CS SKIP LOCKED DATA"),
    )


def control(job_b, p: str) -> dict[str, Any]:
    record = {
        "B control SELECT": two.timed(
            job_b, "B control SELECT", f"SELECT ID, V FROM {p} ORDER BY ID", fetch=True
        ),
        "B control UPDATE": two.timed(
            job_b, "B control UPDATE", f"UPDATE {p} SET V = V WHERE ID = 1"
        ),
    }
    two.end(job_b)
    return record


def lock_round(job_a, job_b, p: str, c: str, label: str, sql: str) -> dict[str, Any]:
    print(f"\n======== A: {label} ========")
    record: dict[str, Any] = {"A lock": two.timed(job_a, f"A {label}", sql, fetch=True)}
    if record["A lock"]["ok"]:
        for b_label, b_sql in b_statements(p, c):
            record[f"B {b_label}"] = two.timed(
                job_b, f"B {b_label}", b_sql, fetch=b_sql.startswith("SELECT")
            )
            two.end(job_b)
    record["A rollback"] = two.end(job_a)
    record.update(control(job_b, p))
    return record


def lock_timeout(job_a, job_b, p: str) -> dict[str, Any]:
    """SET CURRENT LOCK TIMEOUT in B, while A holds row 1 with USE AND KEEP."""
    print("\n======== B: SET CURRENT LOCK TIMEOUT ========")
    record: dict[str, Any] = {
        "A lock": two.timed(
            job_a, "A USE AND KEEP", f"SELECT ID FROM {p} WHERE ID = 1 {KEEP}", fetch=True
        )
    }
    for setting in ("= 0", "NOT WAIT"):
        record[f"SET {setting}"] = two.timed(
            job_b, f"B SET CURRENT LOCK TIMEOUT {setting}", f"SET CURRENT LOCK TIMEOUT {setting}"
        )
        if record[f"SET {setting}"]["ok"]:
            record[f"FOR UPDATE after {setting}"] = two.timed(
                job_b,
                f"B FOR UPDATE after {setting}",
                f"SELECT ID FROM {p} WHERE ID = 1 FOR UPDATE",
                fetch=True,
            )
        two.end(job_b)
    record["reset"] = two.timed(
        job_b, "B SET CURRENT LOCK TIMEOUT NULL", "SET CURRENT LOCK TIMEOUT NULL"
    )
    two.end(job_b)
    record["A rollback"] = two.end(job_a)
    return record


def waiting(job_a, job_b, p: str, how: str) -> dict[str, Any]:
    """B updates row 1 while A holds it; A commits or rolls back after 0.5 s."""
    print(f"\n======== B waits, A {how} after 0.5 s ========")
    record: dict[str, Any] = {
        "A lock": two.timed(
            job_a, "A USE AND KEEP", f"SELECT ID FROM {p} WHERE ID = 1 {KEEP}", fetch=True
        )
    }
    record["B UPDATE row 1"] = two.while_waiting(
        job_b, "B UPDATE row 1", f"UPDATE {p} SET V = V + 1 WHERE ID = 1", (), job_a, how, 0.5
    )
    two.end(job_b)
    two.end(job_a)
    record.update(control(job_b, p))
    return record


def run(job_a, job_b, library: str) -> dict[str, Any]:
    p, c = f"{library}.{PARENT}", f"{library}.{CHILD}"
    rounds: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    try:
        two.create(
            job_a,
            library,
            PARENT,
            "ID INTEGER NOT NULL PRIMARY KEY, V INTEGER",
            "(1, 1), (2, 2), (3, 3)",
        )
        two.create(
            job_a,
            library,
            CHILD,
            "ID INTEGER NOT NULL PRIMARY KEY, PARENT_ID INTEGER, V INTEGER",
            "(10, 1, 1), (20, 2, 2), (30, 3, 3)",
        )
        for label, sql in a_forms(p, c):
            rounds[label] = lock_round(job_a, job_b, p, c, label, sql)
        rounds["SET CURRENT LOCK TIMEOUT"] = lock_timeout(job_a, job_b, p)
        for how in ("commit", "rollback"):
            rounds[f"B waits, A {how}s"] = waiting(job_a, job_b, p, how)
    finally:
        two.end(job_b)
        cleanup = two.drop(job_a, library, (CHILD, PARENT))
    print("\nSummary")
    for name, record in rounds.items():
        for label, result in record.items():
            if isinstance(result, dict):
                print(f"  {name}: {label}: {two.outcome(result)}")
    return {"rounds": rounds, "cleanup": cleanup}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the tables")
    args = parser.parse_args(argv)
    jobs: list = []
    try:
        settings = Settings.from_env(need_credentials=True)
        library = settings.default_library
        if not library:
            raise ProbeError("config", "DB2I_DEFAULT_LIBRARY is not set", 1)
        jobs.append(two.open_job(settings, library))
        two.checks(jobs[0], library, (PARENT, CHILD))
        if not args.execute:
            print("\nDry run: nothing was changed. Re-run with --execute to apply.")
            return 0
        jobs.append(two.open_job(settings, library))
        result = run(jobs[0], jobs[1], library)
        print(f"\nresult saved to {write_result('lib_select_for_update', result, settings)}")
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
