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

Follow-up (--followup, approved separately on #162): what releases the lock. The
same table, the same cleanup, never more than two connections. Each case on a free
table (B's SELECT must succeed first, else the probe stops): A locks IN EXCLUSIVE
MODE, then tries one release (the driver's rollback or commit, the SQL ROLLBACK or
COMMIT, DLCOBJ through QSYS2.QCMDEXC, closing the connection), with A in a
transaction or in autocommit, TRUEAUTOCOMMIT 0 or 1. After each case: B's SELECT and
INSERT (rolled back), and the table's rows of QSYS2.OBJECT_LOCK_INFO (read-only). A
lock still held is released before the next case (DLCOBJ, else A reconnects).

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_lock_table              # dry run: checks only
    bin/probe --approved <link> lib_lock_table -- --execute
    bin/probe --approved <link> lib_lock_table -- --execute --followup
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from typing import Any

import _twojobs as two
from _common import ProbeError, Settings, run_query, write_result

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


# --- Follow-up (#162): what releases the lock --------------------------------------

BACKEND = {"trueautocommit": "1", "autocommit": False}  # the backend's job A


class Followup:
    def __init__(self, settings: Settings, jobs: list, library: str):
        self.settings, self.jobs, self.library = settings, jobs, library
        self.t = f"{library}.{TABLE}"
        self.short = TABLE
        self.a_attrs = dict(BACKEND)
        self.a_job = ""

    @property
    def a(self):
        return self.jobs[0]

    @property
    def b(self):
        return self.jobs[1]

    def reopen_a(self, trueautocommit: str, autocommit: bool) -> None:
        """Close job A, then open it again: never more than two connections."""
        with contextlib.suppress(Exception):
            self.a.rollback()
        with contextlib.suppress(Exception):
            self.a.close()
        self.jobs[0] = two.open_job(
            self.settings, self.library, trueautocommit=trueautocommit, autocommit=autocommit
        )
        self.a_attrs = {"trueautocommit": trueautocommit, "autocommit": autocommit}
        self.a_job = self.job_name(self.a)

    @staticmethod
    def job_name(conn) -> str:
        result = run_query(conn, "job", "SELECT QSYS2.JOB_NAME AS J FROM SYSIBM.SYSDUMMY1")
        return result["rows"][0]["J"] if result["ok"] and result["rows"] else ""

    def locks(self) -> list[dict[str, Any]] | str:
        """This table's rows of QSYS2.OBJECT_LOCK_INFO, read by job B (read-only)."""
        result = run_query(
            self.b,
            "OBJECT_LOCK_INFO",
            "SELECT * FROM QSYS2.OBJECT_LOCK_INFO WHERE OBJECT_SCHEMA = ? AND OBJECT_NAME = ?",
            (self.library, self.short),
        )
        two.end(self.b)
        if not result["ok"]:
            return f"error {result.get('sqlstate')} {result.get('message', '')[:160]}"
        for row in result["rows"]:
            print(
                f"  lock: {row.get('JOB_NAME')} {row.get('LOCK_STATE')} "
                f"{row.get('LOCK_STATUS')} {row.get('LOCK_SCOPE')} {row.get('MEMBER_NAME')}"
            )
        return result["rows"]

    def a_locks(self, rows) -> list[dict[str, Any]]:
        return (
            [r for r in rows if isinstance(r, dict) and r.get("JOB_NAME") == self.a_job]
            if isinstance(rows, list)
            else []
        )

    def b_check(self) -> dict[str, Any]:
        record = {
            "SELECT": two.timed(
                self.b, "B SELECT", f"SELECT ID, V FROM {self.t} ORDER BY ID", fetch=True
            )
        }
        if record["SELECT"]["ok"]:
            record["INSERT"] = two.timed(self.b, "B INSERT", f"INSERT INTO {self.t} VALUES (9, 9)")
        else:
            record["INSERT"] = "not run: the SELECT was blocked"
        two.end(self.b)
        return record

    def dlcobj(self, rows) -> list[dict[str, Any]]:
        """DLCOBJ in job A for each of A's locks on this table, with its own lock state."""
        results = []
        for row in self.a_locks(rows):
            state = str(row.get("LOCK_STATE") or "").strip()
            member = str(row.get("MEMBER_NAME") or "").strip()
            target = f"{self.library}/{self.short} *FILE {state}" + (f" {member}" if member else "")
            results.append(
                two.timed(
                    self.a,
                    f"A DLCOBJ {state} {member}".rstrip(),
                    f"CALL QSYS2.QCMDEXC('DLCOBJ OBJ(({target}))')",
                )
            )
        return results

    def release_leftover(self, record: dict[str, Any]) -> None:
        """Before the next case: a lock still held goes (DLCOBJ, else A reconnects)."""
        rows = record["locks after"]
        if not self.a_locks(rows) and record["B after"]["SELECT"]["ok"]:
            return
        record["leftover: DLCOBJ"] = self.dlcobj(rows)
        record["leftover: locks"] = self.locks()
        if self.a_locks(record["leftover: locks"]):
            record["leftover: A reconnected"] = True
            self.reopen_a(**self.a_attrs)

    def case(self, name: str, release) -> dict[str, Any]:
        print(f"\n======== {name} ========")
        record: dict[str, Any] = {"A": dict(self.a_attrs, cmt="*CS", job=self.a_job)}
        record["B before"] = two.timed(
            self.b, "B SELECT before", f"SELECT ID FROM {self.t}", fetch=True
        )
        two.end(self.b)
        if not record["B before"]["ok"]:
            raise ProbeError("check", f"{name}: the table is not free before the case; stopping")
        record["A lock"] = two.timed(
            self.a, "A LOCK TABLE EXCLUSIVE", f"LOCK TABLE {self.t} IN EXCLUSIVE MODE"
        )
        record["locks while held"] = self.locks()
        record["release"] = release(record)
        record["locks after"] = self.locks()
        record["B after"] = self.b_check()
        self.release_leftover(record)
        return record

    def run(self) -> dict[str, Any]:
        cases: dict[str, Any] = {}
        sql = lambda label, stmt: lambda record: two.timed(self.a, label, stmt)  # noqa: E731

        def driver(how):
            return lambda record: two.end(self.a, how)

        def dlcobj(record):
            return self.dlcobj(record["locks while held"])

        def close(record):
            self.reopen_a(**BACKEND)
            return "A closed and opened again"

        self.reopen_a(**BACKEND)
        cases["2. transaction, driver rollback"] = self.case("2", driver("rollback"))
        cases["3. transaction, SQL ROLLBACK"] = self.case("3", sql("A ROLLBACK", "ROLLBACK"))
        cases["4a. transaction, driver commit"] = self.case("4a", driver("commit"))
        cases["4b. transaction, SQL COMMIT"] = self.case("4b", sql("A COMMIT", "COMMIT"))
        cases["5. transaction, DLCOBJ"] = self.case("5", dlcobj)
        self.reopen_a(trueautocommit="0", autocommit=True)
        cases["1. autocommit, TRUEAUTOCOMMIT=0, driver rollback"] = self.case(
            "1", driver("rollback")
        )
        self.reopen_a(trueautocommit="1", autocommit=True)
        cases["6. autocommit, TRUEAUTOCOMMIT=1, driver rollback"] = self.case(
            "6", driver("rollback")
        )
        self.reopen_a(**BACKEND)
        cases["7. transaction, connection closed"] = self.case("7", close)
        return cases


def run_followup(settings: Settings, jobs: list, library: str) -> dict[str, Any]:
    follow = Followup(settings, jobs, library)
    cases: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    try:
        two.create(jobs[0], library, TABLE, "ID INTEGER, V INTEGER", "(1, 1), (2, 2)")
        follow.short = two.system_name(jobs[0], library, TABLE)
        two.end(jobs[0])
        cases = follow.run()
    finally:
        # The last resort: closing job A releases its locks (IBM's LOCK TABLE page).
        two.end(jobs[1])
        with contextlib.suppress(Exception):
            follow.reopen_a(**BACKEND)
        cleanup = two.drop(jobs[0], library, (TABLE,))
    print("\nSummary")
    for name, record in cases.items():
        after = record["B after"]
        held = (
            len(follow.a_locks(record["locks after"]))
            if isinstance(record["locks after"], list)
            else "?"
        )
        print(f"  {name}: B SELECT {two.outcome(after['SELECT'])}; A's locks left: {held}")
    return {"followup": cases, "cleanup": cleanup}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--execute", action="store_true", help="create, use and drop the table")
    parser.add_argument("--followup", action="store_true", help="the cases of what releases it")
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
        if args.followup:
            result = run_followup(settings, jobs, library)
            name = "lib_lock_table_followup"
        else:
            result = run(jobs[0], jobs[1], library)
            name = "lib_lock_table"
        print(f"\nresult saved to {write_result(name, result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        for conn in reversed(jobs):
            two.end(conn)
            with contextlib.suppress(Exception):
                conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
