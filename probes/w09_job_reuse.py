"""Write probe 09: does the database host server reset INQMSGRPY on disconnect?

Changes only the probe's own server job (QZDASOINIT / QZDASSINIT), which
the probe sets to *SYSRPYL and deliberately does NOT restore before it
disconnects. Two connections, strictly one after the other. Not part of
probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_job_reuse

1. Connection 1: read the job name, its INQUIRY_MESSAGE_REPLY and the
   prestart job reuse count; CHGJOB INQMSGRPY(*SYSRPYL); read it back;
   disconnect without restoring.
2. Connection 2: look the first job up by name in QSYS2.JOB_INFO (status
   and INQUIRY_MESSAGE_REPLY after the disconnect); report this job's name
   and reply too (the server may hand out the same job again).

Question: is the attribute reset by the host server when the client
disconnects and the prestart job waits for reuse, or does the next client
of that job inherit it? The backend restores it explicitly either way.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from _common import ProbeError, Settings, connect, run_statement, run_values, write_result

VALID = ("*RQD", "*DFT", "*SYSRPYL")
JOB_SQL = (
    "SELECT JOB_NAME, JOB_STATUS, INQUIRY_MESSAGE_REPLY "
    "FROM TABLE(QSYS2.JOB_INFO(JOB_STATUS_FILTER => '*ALL', JOB_USER_FILTER => 'QUSER')) X "
    "WHERE JOB_NAME = {name}"
)


def value(result: dict[str, Any], column: str) -> str | None:
    if not result["ok"] or len(result.get("rows", [])) != 1:
        return None
    return result["rows"][0][column]["repr"].strip("'\" ")


def main(argv: list[str]) -> int:
    steps: list[dict[str, Any]] = []
    first_job = original = None
    try:
        settings = Settings.from_env(need_credentials=True)

        print("\n======== 1. Connection 1: change, disconnect without restoring ========")
        conn = connect(settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1"}, autocommit=True)
        try:
            job = run_values(conn, "connection 1: this job", JOB_SQL.format(name="QSYS2.JOB_NAME"))
            steps.append(job)
            first_job, original = value(job, "JOB_NAME"), value(job, "INQUIRY_MESSAGE_REPLY")
            steps.append(
                run_values(
                    conn,
                    "connection 1: prestart job reuse count",
                    "SELECT V_PJ_REUSE_COUNT, V_PJ_MAXUSE_COUNT "
                    "FROM TABLE(QSYS2.GET_JOB_INFO('*')) X",
                )
            )
            if not first_job or original not in VALID:
                raise ProbeError(
                    "check", f"job or reply not readable ({first_job}, {original}); nothing changed"
                )
            steps.append(
                run_statement(
                    conn,
                    "CHGJOB INQMSGRPY(*SYSRPYL)",
                    "CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY(*SYSRPYL)')",
                )
            )
            steps.append(
                run_values(
                    conn, "connection 1: after CHGJOB", JOB_SQL.format(name="QSYS2.JOB_NAME")
                )
            )
        finally:
            conn.close()
        time.sleep(3)  # let the host server return the job to the pool

        print("\n======== 2. Connection 2: the first job after the disconnect ========")
        conn = connect(settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1"}, autocommit=True)
        try:
            after = run_values(
                conn, "first job after disconnect", JOB_SQL.format(name=f"'{first_job}'")
            )
            steps.append(after)
            this = run_values(conn, "connection 2: this job", JOB_SQL.format(name="QSYS2.JOB_NAME"))
            steps.append(this)
        finally:
            conn.close()
        result = {
            "steps": steps,
            "first_job": first_job,
            "original": original,
            "first_job_after_disconnect": value(after, "INQUIRY_MESSAGE_REPLY"),
            "first_job_status_after_disconnect": value(after, "JOB_STATUS"),
            "second_job": value(this, "JOB_NAME"),
            "second_job_reply": value(this, "INQUIRY_MESSAGE_REPLY"),
        }
        print("\nSummary")
        for key in list(result)[1:]:
            print(f"  {key:<36} {result[key]}")
        print(f"\nresult saved to {write_result('w09_job_reuse', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
