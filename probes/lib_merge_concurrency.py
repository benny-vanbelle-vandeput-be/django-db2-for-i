"""MERGE with two jobs inserting the same key (issue #238).

THIS CHANGES THE IBM i: one table, DJDB2I_MRGPROBE (ID INTEGER PRIMARY KEY,
K INTEGER NOT NULL UNIQUE, V INTEGER), in the journaled default library, recorded
on the cleanup list (tests/table_registry.py) before its CREATE TABLE, its record
wait time set with CHGPF WAITRCD(2), and dropped at the end, also after a failure.

Approved by the maintainer on issue #238 (comment 6801593663), as described there,
plus: job A commits once within the 2-second wait and once after it, and the
result records what job B gets in each (SQLCODE or rows).

Two connections at the same time (jobs A and B, the backend's attributes, *CS),
with the MERGE the backend writes for bulk_create(ignore_conflicts=True) and for
update_conflicts (the conflict on the unique key K). After each case both jobs
roll back and the table's rows are deleted. The *RR cases close both connections
and open them again with CMT=4. No retries of a connection, never more than two at
the same time. Run only through the PUB400 lock. Not part of probes/run.py.

Usage (on the host; bin/probe checks the approval on GitHub first):
    bin/probe --approved <link> lib_merge_concurrency              # dry run: checks only
    bin/probe --approved <link> lib_merge_concurrency -- --execute
"""

from __future__ import annotations

import argparse
import sys
import threading
from typing import Any

import _twojobs as two
from _common import ProbeError, Settings, write_result

TABLE = "DJDB2I_MRGPROBE"
RACE_KEYS = 20


def merge(t: str, rows: int, update: bool) -> str:
    """The backend's MERGE shape (golden dml/bulk_insert_*_conflicts), the conflict on K."""
    one = "(CAST(? AS INTEGER), CAST(? AS INTEGER), CAST(? AS INTEGER))"
    matched = "WHEN MATCHED THEN UPDATE SET TGT.V = SRC.V " if update else ""
    return (
        f"MERGE INTO {t} AS TGT USING (VALUES {', '.join([one] * rows)}) AS SRC (ID, K, V) "
        f"ON (TGT.K = SRC.K) {matched}"
        "WHEN NOT MATCHED THEN INSERT (ID, K, V) VALUES (SRC.ID, SRC.K, SRC.V)"
    )


class Cases:
    def __init__(self, job_a, job_b, t: str, update: bool = False):
        self.a, self.b, self.t, self.update = job_a, job_b, t, update

    def a_merge(self, key: int) -> dict[str, Any]:
        return two.timed(self.a, f"A merges K={key}", merge(self.t, 1, self.update), (key, key, 1))

    def b_sql(self) -> str:
        return merge(self.t, 1, self.update)

    def rows(self, job) -> dict[str, Any]:
        return two.timed(job, "rows", f"SELECT ID, K, V FROM {self.t} ORDER BY K", fetch=True)

    def reset(self) -> None:
        two.end(self.b)
        two.end(self.a)
        two.timed(self.a, "reset", f"DELETE FROM {self.t}")
        two.end(self.a, "commit")

    def uncommitted(self) -> dict[str, Any]:
        """A merges K=1 and does not commit; B merges the same key."""
        record = {"A": self.a_merge(1)}
        record["B"] = two.timed(self.b, "B merges K=1", self.b_sql(), (100, 1, 2))
        record["A rollback"] = two.end(self.a)
        self.reset()
        return record

    def a_ends_while_b_waits(self, how: str, after: float, retry: bool = False) -> dict[str, Any]:
        record = {"A": self.a_merge(1)}
        record["B"] = two.while_waiting(
            self.b, "B merges K=1", self.b_sql(), (100, 1, 2), self.a, how, after
        )
        record["B sees"] = self.rows(self.b)
        two.end(self.b)
        if retry:
            # The retry of Known Limitations, once A committed: in a transaction, then autocommit.
            record["B retry in a transaction"] = two.timed(
                self.b, "B retry (transaction)", self.b_sql(), (100, 1, 2)
            )
            record["B retry commit"] = two.end(self.b, "commit")
            self.b.autocommit = True
            try:
                record["B retry in autocommit"] = two.timed(
                    self.b, "B retry (autocommit)", self.b_sql(), (101, 1, 3)
                )
            finally:
                self.b.autocommit = False
            record["after the retries"] = self.rows(self.b)
        self.reset()
        return record

    def batch(self) -> dict[str, Any]:
        """A merges K=3 uncommitted; B merges a batch of K=1..5."""
        record = {"A": self.a_merge(3)}
        params = tuple(v for key in range(1, 6) for v in (100 + key, key, 2))
        record["B batch K=1..5"] = two.timed(
            self.b, "B batch K=1..5", merge(self.t, 5, self.update), params
        )
        record["B sees before rollback"] = self.rows(self.b)
        record["A rollback"] = two.end(self.a)
        self.reset()
        return record

    def race(self) -> dict[str, Any]:
        """Both jobs merge the same new keys, one statement and a commit each, at the same time."""
        tallies: dict[str, dict[str, int]] = {}

        def loop(name: str, job, base: int) -> None:
            tally: dict[str, int] = {}
            for key in range(1, RACE_KEYS + 1):
                result = two.timed(job, f"{name} K={key}", self.b_sql(), (base + key, key, base))
                word = "ok" if result["ok"] else result.get("sqlcode", "?")
                tally[word] = tally.get(word, 0) + 1
                two.end(job, "commit" if result["ok"] else "rollback")
            tallies[name] = tally

        threads = [
            threading.Thread(target=loop, args=("A", self.a, 1000), daemon=True),
            threading.Thread(target=loop, args=("B", self.b, 2000), daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=300)
        record: dict[str, Any] = {"tallies": tallies, "rows": self.rows(self.a)}
        two.end(self.a)
        self.reset()
        return record


def series(job_a, job_b, t: str, update: bool, full: bool) -> dict[str, Any]:
    cases = Cases(job_a, job_b, t, update)
    record: dict[str, Any] = {}
    print(f"\n======== {'update_conflicts' if update else 'ignore_conflicts'} ========")
    record["A uncommitted, B merges"] = cases.uncommitted()
    record["A commits within the wait (0.5 s)"] = cases.a_ends_while_b_waits(
        "commit", 0.5, retry=full
    )
    record["A commits after the wait (3 s)"] = cases.a_ends_while_b_waits("commit", 3.0)
    record["A rolls back within the wait (0.5 s)"] = cases.a_ends_while_b_waits("rollback", 0.5)
    if full:
        record["a batch, one row in conflict"] = cases.batch()
        record[f"race over {RACE_KEYS} keys"] = cases.race()
    return record


def run(settings: Settings, jobs: list, library: str) -> dict[str, Any]:
    t = f"{library}.{TABLE}"
    rounds: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    try:
        two.create(
            jobs[0],
            library,
            TABLE,
            "ID INTEGER NOT NULL PRIMARY KEY, K INTEGER NOT NULL UNIQUE, V INTEGER",
            "(0, 0, 0)",
        )
        two.timed(jobs[0], "reset", f"DELETE FROM {t}")
        two.end(jobs[0], "commit")
        for update in (False, True):
            name = "update_conflicts" if update else "ignore_conflicts"
            rounds[f"*CS, {name}"] = series(jobs[0], jobs[1], t, update, full=True)
        # *RR: both connections closed and opened again with CMT=4, never more than two.
        for conn in reversed(jobs):
            two.end(conn)
            conn.close()
        jobs.clear()
        jobs.append(two.open_job(settings, library, cmt="4"))
        jobs.append(two.open_job(settings, library, cmt="4"))
        rounds["*RR, ignore_conflicts"] = series(jobs[0], jobs[1], t, False, full=False)
    finally:
        if jobs:
            two.end(jobs[-1])
            cleanup = two.drop(jobs[0], library, (TABLE,))
    print("\nSummary")
    for name, series_record in rounds.items():
        for case, record in series_record.items():
            for label, result in record.items():
                if isinstance(result, dict) and "ok" in result:
                    print(f"  {name}: {case}: {label}: {two.outcome(result)}")
                elif label == "tallies":
                    print(f"  {name}: {case}: {result}")
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
        result = run(settings, jobs, library)
        print(f"\nresult saved to {write_result('lib_merge_concurrency', result, settings)}")
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
