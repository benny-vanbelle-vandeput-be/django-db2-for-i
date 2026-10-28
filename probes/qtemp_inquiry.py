"""Write probe 08: the inquiry message behind DROP COLUMN on a table with rows.

Changes only QTEMP and the probe's own job (both gone when the connection
closes); every job attribute it changes is set back before it ends. No
library, no system object, no reply list entry is changed. Not part of
probes/run.py.

Usage (inside the "tests" container):
    nox -s probe_inquiry

Question: in the IBM i tests, ALTER TABLE ... DROP COLUMN on a table with
rows was cancelled (HY008). Which message is sent, and can the backend
answer it for its own ALTER TABLE statements only?

1. Read the job's inquiry message reply attribute (QSYS2.JOB_INFO), the
   default reply of CPA32B2 and the system reply list entries for it.
2. Reproduce: QTEMP table with one row, DROP COLUMN; read the job log.
3. Option A: CHGJOB INQMSGRPY(*SYSRPYL) (authority? does the system reply
   list answer it?), DROP COLUMN again, then set the attribute back to the
   value read in step 1 (skipped entirely if that value cannot be read).
4. Option B: QSYS2.OVERRIDE_QAQQINI(1) makes a job-level copy of QAQQINI in
   QTEMP; list its options to see whether any controls inquiry messages;
   OVERRIDE_QAQQINI(3) removes the override.
"""

from __future__ import annotations

import sys
from typing import Any

from _common import ProbeError, Settings, connect, run_statement, run_values, write_result

TABLE = "QTEMP.DJINQ"


def inquiry_reply(vals, label: str) -> str | None:
    """The job's INQMSGRPY attribute (*RQD, *DFT, *SYSRPYL), or None."""
    result = vals(
        label,
        "SELECT INQUIRY_MESSAGE_REPLY FROM TABLE(QSYS2.JOB_INFO(JOB_USER_FILTER => 'QUSER')) X "
        "WHERE JOB_NAME = QSYS2.JOB_NAME",
    )
    if not result["ok"] or len(result["rows"]) != 1:
        return None
    return result["rows"][0]["INQUIRY_MESSAGE_REPLY"]["repr"].strip("'\" ")


def run(conn) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    def stmt(label: str, sql: str) -> dict[str, Any]:
        result = run_statement(conn, label, sql)
        steps.append(result)
        return result

    def vals(label: str, sql: str) -> dict[str, Any]:
        result = run_values(conn, label, sql)
        steps.append(result)
        return result

    def joblog(label: str) -> dict[str, Any]:
        return vals(
            label,
            "SELECT MESSAGE_ID, MESSAGE_TYPE, SEVERITY, VARCHAR(MESSAGE_TEXT, 200) AS TEXT "
            "FROM TABLE(QSYS2.JOBLOG_INFO('*')) X "
            "ORDER BY ORDINAL_POSITION DESC FETCH FIRST 8 ROWS ONLY",
        )

    def fresh(label: str, columns: str) -> None:
        """A new, empty QTEMP table (CREATE OR REPLACE would try to keep the rows)."""
        run_statement(conn, f"{label}: drop old table", f"DROP TABLE {TABLE}")
        stmt(f"{label}: create", f"CREATE TABLE {TABLE} ({columns})")

    def reproduce(label: str) -> bool:
        fresh(label, "A INTEGER, B INTEGER")
        stmt(f"{label}: insert", f"INSERT INTO {TABLE} VALUES (1, 2) WITH NC")
        dropped = stmt(
            f"{label}: DROP COLUMN on a table with a row", f"ALTER TABLE {TABLE} DROP COLUMN B"
        )
        joblog(f"{label}: job log after DROP COLUMN")
        return dropped["ok"]

    print("\n======== 1. Job attribute and system reply list ========")
    original = inquiry_reply(vals, "job: inquiry message reply")
    vals(
        "CPA32B2: default reply",
        "SELECT MESSAGE_ID, DEFAULT_REPLY, VARCHAR(MESSAGE_TEXT, 80) AS TEXT "
        "FROM QSYS2.MESSAGE_FILE_DATA WHERE MESSAGE_FILE_LIBRARY = 'QSYS' "
        "AND MESSAGE_FILE = 'QCPFMSG' AND MESSAGE_ID = 'CPA32B2'",
    )
    vals(
        "system reply list: CPA32B2 entries",
        "SELECT SEQUENCE_NUMBER, MESSAGE_ID, MESSAGE_REPLY, COMPARISON_DATA, "
        "COMPARISON_DATA_OFFSET FROM QSYS2.REPLY_LIST_INFO WHERE MESSAGE_ID = 'CPA32B2'",
    )

    print("\n======== 2. Reproduce ========")
    baseline = reproduce("baseline")

    print("\n======== 2b. Other ALTER TABLE changes on a table with a row ========")
    alters: dict[str, bool] = {}
    for label, column, value, alter in [
        ("INTEGER -> SMALLINT (narrowing, value fits)", "INTEGER", "2", "SMALLINT"),
        ("INTEGER -> BIGINT (widening)", "INTEGER", "2", "BIGINT"),
        ("VARCHAR(10) -> VARCHAR(5) (narrowing, value fits)", "VARCHAR(10)", "'ab'", "VARCHAR(5)"),
        ("VARCHAR(5) -> VARCHAR(10) (widening)", "VARCHAR(5)", "'ab'", "VARCHAR(10)"),
        ("DECIMAL(9, 2) -> DECIMAL(5, 2) (narrowing)", "DECIMAL(9, 2)", "1.5", "DECIMAL(5, 2)"),
        (
            "NVARCHAR(10) -> NVARCHAR(5) (narrowing, value fits)",
            "NVARCHAR(10)",
            "'ab'",
            "NVARCHAR(5)",
        ),
    ]:
        fresh(label, f"A INTEGER, B {column}")
        stmt(f"{label}: insert", f"INSERT INTO {TABLE} VALUES (1, {value}) WITH NC")
        alters[label] = stmt(
            f"{label}: ALTER COLUMN",
            f"ALTER TABLE {TABLE} ALTER COLUMN B SET DATA TYPE {alter}",
        )["ok"]
        if not alters[label]:
            joblog(f"{label}: job log")
    fresh("ADD COLUMN NOT NULL WITH DEFAULT", "A INTEGER")
    stmt("ADD COLUMN NOT NULL WITH DEFAULT: insert", f"INSERT INTO {TABLE} VALUES (1) WITH NC")
    alters["ADD COLUMN NOT NULL DEFAULT 0"] = stmt(
        "ADD COLUMN NOT NULL DEFAULT 0",
        f"ALTER TABLE {TABLE} ADD COLUMN C INTEGER NOT NULL DEFAULT 0",
    )["ok"]
    fresh("empty table", "A INTEGER, B INTEGER")
    alters["DROP COLUMN on an empty table"] = stmt(
        "DROP COLUMN on an empty table", f"ALTER TABLE {TABLE} DROP COLUMN B"
    )["ok"]
    for label, ok in alters.items():
        print(f"  {label:<55} {'ok' if ok else 'CANCELLED/FAILED'}")

    print("\n======== 3. Option A: CHGJOB INQMSGRPY(*SYSRPYL) ========")
    option_a: bool | None = None
    changed = {"ok": False}
    reset_ok: bool | None = None
    if original not in ("*RQD", "*DFT", "*SYSRPYL"):
        print(f"\n# original reply {original!r} unknown: option A skipped, nothing changed")
    else:
        changed = stmt(
            "CHGJOB INQMSGRPY(*SYSRPYL)", "CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY(*SYSRPYL)')"
        )
    if changed["ok"]:
        try:
            inquiry_reply(vals, "job: inquiry message reply after CHGJOB")
            option_a = reproduce("with *SYSRPYL")
        finally:
            stmt(
                f"reset: CHGJOB INQMSGRPY({original})",
                f"CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY({original})')",
            )
            reset_ok = inquiry_reply(vals, "job: inquiry message reply after reset") == original

    print("\n======== 4. Option B: QAQQINI options ========")
    copied = stmt(
        "OVERRIDE_QAQQINI(1): job copy in QTEMP", "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')"
    )
    options: list[str] = []
    if copied["ok"]:
        try:
            listed = vals(
                "QAQQINI options (all)",
                "SELECT VARCHAR(QQPARM, 60) AS PARM FROM QTEMP.QAQQINI ORDER BY QQPARM",
            )
            options = [row["PARM"]["repr"].strip("'\" ") for row in listed.get("rows", [])]
        finally:
            stmt(
                "OVERRIDE_QAQQINI(3): remove the override", "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')"
            )
    related = [
        o for o in options if any(w in o for w in ("INQ", "REPLY", "MESSAGE", "ALTER", "DDL"))
    ]
    print(f"\n# QAQQINI options mentioning INQ/REPLY/MESSAGE/ALTER/DDL: {related or 'none'}")

    stmt("drop probe table", f"DROP TABLE {TABLE}")
    return {
        "steps": steps,
        "original_inqmsgrpy": original,
        "baseline_drop_ok": baseline,
        "chgjob_ok": changed["ok"],
        "reset_ok": reset_ok,
        "option_a_drop_ok": option_a,
        "other_alters_ok": alters,
        "qaqqini_options": options,
        "qaqqini_related": related,
    }


def main(argv: list[str]) -> int:
    conn = None
    try:
        settings = Settings.from_env(need_credentials=True)
        # The backend's settings: commitment control, autocommit (schema editor).
        conn = connect(settings, {"CMT": "1", "TRUEAUTOCOMMIT": "1"}, autocommit=True)
        result = run(conn)
        print(f"\nresult saved to {write_result('qtemp_inquiry', result, settings)}")
    except ProbeError as exc:
        print(f"\nPROBE FAILED [{exc.category}]: {exc}", file=sys.stderr)
        return exc.exit_code
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
