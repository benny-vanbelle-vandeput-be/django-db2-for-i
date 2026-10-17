"""Write probe 11: does the job CCSID change finding B (escaped quote in a DEFAULT)?

Changes only QTEMP and the probe's own job: CHGJOB CCSID(37), which is set
back to the value read before (approved by the project owner). One
connection. Refuses to change anything if the original CCSID cannot be read.
Not part of probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_job_ccsid

Finding B (docs/IBMI_NOTES.md, "String encoding investigation"):
``DEFAULT 'O''Brien'`` is stored as ``O''Brien`` (NVARCHAR) or garbled
(CHAR/VARCHAR), with every client-side setting tried, in job CCSID 273.
This probe runs the same B checks (probes/w10_encoding.py) in job CCSID 273
and again after CHGJOB CCSID(37).

Note: the driver learns the job CCSID at connect and keeps converting
statement text to 273; the statements here are ASCII only, and the quote
and letters have the same code points in CCSID 273 and 37.
"""

from __future__ import annotations

import sys
from typing import Any

from _common import ProbeError, Settings, connect, write_result
from w10_encoding import BACKEND, Probe, check_b, print_step

CCSID_SQL = (
    "SELECT CCSID, DEFAULT_CCSID FROM TABLE(QSYS2.ACTIVE_JOB_INFO("
    "JOB_NAME_FILTER => '*', DETAILED_INFO => 'ALL')) X WHERE JOB_NAME = QSYS2.JOB_NAME"
)
TARGET = 37


def job_ccsid(probe: Probe, label: str) -> tuple[int, int] | None:
    step = probe.run(label, CCSID_SQL)
    print_step(step)
    rows = step.get("rows") if step["ok"] else None
    if not rows or len(rows) != 1:
        return None
    ccsid, default = rows[0]
    return int(ccsid), int(default)


def run(probe: Probe) -> dict[str, Any]:
    result: dict[str, Any] = {}
    print("\n======== 1. Job CCSID before ========")
    original = job_ccsid(probe, "job CCSID before")
    result["original"] = original
    if original is None or not 1 <= original[0] <= 65535:
        raise ProbeError("check", f"original job CCSID not readable ({original}); nothing changed")
    print("\n======== 2. B in the original job CCSID ========")
    result["B_original"] = check_b(probe)
    print(f"\n======== 3. CHGJOB CCSID({TARGET}) ========")
    changed = probe.run(
        f"CHGJOB CCSID({TARGET})",
        f"CALL QSYS2.QCMDEXC('CHGJOB CCSID({TARGET})')",
        fetch=False,
    )
    print_step(changed)
    result["chgjob_ok"] = changed["ok"] or changed["error"]
    if changed["ok"]:
        try:
            result["after_change"] = job_ccsid(probe, f"job CCSID after CHGJOB CCSID({TARGET})")
            print(f"\n======== 4. B in job CCSID {TARGET} ========")
            result["B_changed"] = check_b(probe)
        finally:
            print("\n======== 5. Restore ========")
            restore = probe.run(
                f"restore: CHGJOB CCSID({original[0]})",
                f"CALL QSYS2.QCMDEXC('CHGJOB CCSID({original[0]})')",
                fetch=False,
            )
            print_step(restore)
            restored = job_ccsid(probe, "job CCSID after restore")
            result["restored"] = restored
            result["restore_ok"] = restored == original
            print(f"  restored to the original: {result['restore_ok']}")
    return result


def main(argv: list[str]) -> int:
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        conn = connect(settings, BACKEND, autocommit=True)
        probe = Probe(conn)
        result = run(probe)
        result["steps"] = probe.steps
        print(f"\nresult saved to {write_result('w11_job_ccsid', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
