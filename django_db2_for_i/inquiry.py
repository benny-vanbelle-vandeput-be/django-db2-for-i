"""Inquiry message CPA32B2 on ALTER TABLE: suppressed per job, or answered.

Db2 for i sends inquiry message CPA32B2 ("Change of file may cause data to
be lost. (C I)") for DROP COLUMN, narrowing column changes and SET NOT NULL,
also on empty tables. Its default reply is C, and database host server jobs
reply with *RQD (job description QGPL/QDFTSVR), so the statement is cancelled
(CPD32CE, CPF7304) and the driver reports HY008 (probe ``probe_inquiry``,
docs/IBMI_NOTES.md).

**Suppressed per job** (``OPTIONS["suppress_inquiry_messages"]``, default
True): the schema editor sets the QAQQINI option SUPPRESS_INQUIRY_MESSAGES
to *YES for its own job (``QSYS2.OVERRIDE_QAQQINI``, a copy in QTEMP, no
authority needed) around the field changes of migrations, and discards the
copy when the outermost schema editor exits (probes ``qaqqini_inquiry`` and
``qaqqini_lifecycle``). No administrator is involved. A ROLLBACK undoes
neither step, so the discard always runs explicitly.

**Answered by the system reply list** (opt-in):
``OPTIONS["inquiry_message_reply"] = "*SYSRPYL"`` lets the system reply list
answer it, if an administrator added an entry
``ADDRPYLE SEQNBR(...) MSGID(CPA32B2) RPY('I')``. The backend then changes
the job's INQMSGRPY for the whole connection and restores the value it read
before when the connection closes. Without the option it never touches the
job attribute.

Everything here works on a DB-API cursor; no driver-specific code.
"""

from __future__ import annotations

import re

OPTION = "inquiry_message_reply"
VALID_REPLIES = ("*RQD", "*DFT", "*SYSRPYL")

JOB_NAME_SQL = "SELECT QSYS2.JOB_NAME FROM SYSIBM.SYSDUMMY1"
# number/user/name, e.g. 974600/QUSER/QZDASSINIT
_JOB_NAME = re.compile(r"^\d{6}/([A-Z0-9#@$_]{1,10})/[A-Z0-9#@$_]{1,10}$")

# Inquiry message and diagnostics of a cancelled ALTER TABLE (job log).
CANCEL_MESSAGES = ("CPA32B2", "CPD32CE")
CANCELLED_SQLSTATE = "HY008"
JOB_LOG_SQL = (
    "SELECT MESSAGE_ID FROM TABLE(QSYS2.JOBLOG_INFO('*')) X "
    "ORDER BY ORDINAL_POSITION DESC FETCH FIRST 10 ROWS ONLY"
)

# OVERRIDE_QAQQINI: 1 creates the job's QAQQINI copy in QTEMP (it inherits
# the job's current options), 2 sets one option, 3 discards the copy. 3 also
# succeeds without a copy, and 1 again keeps it (probe qaqqini_lifecycle).
SUPPRESS_OPTION = "suppress_inquiry_messages"
SUPPRESS_SQL = (
    "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')",
    "CALL QSYS2.OVERRIDE_QAQQINI(2, 'SUPPRESS_INQUIRY_MESSAGES', '*YES')",
)
DISCARD_SQL = "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')"

# Why CPA32B2 was not suppressed for a cancelled statement.
NOT_IN_FIELD_CHANGE = "outside"
SUPPRESSION_OFF = "off"
SUPPRESSION_UNAVAILABLE = "unavailable"
SUPPRESSION_FAILED = "failed"

ADDRPYLE = "ADDRPYLE SEQNBR(<free number>) MSGID(CPA32B2) RPY('I')"
# Where the user documentation explains it (docs/user/, mirrored to the wiki).
DOCS = '"ALTER TABLE that may lose data" in docs/user/IBM-i-Requirements.md'


class InquiryReplyError(Exception):
    """The job's inquiry message reply could not be read; nothing was changed."""


def normalize_reply(value: object) -> str:
    """``"*sysrpyl"`` -> ``"*SYSRPYL"``; ValueError for anything else."""
    reply = str(value).strip().upper() if isinstance(value, str) else ""
    if reply not in VALID_REPLIES:
        raise ValueError(
            f"invalid inquiry message reply {value!r}; use one of {', '.join(VALID_REPLIES)}"
        )
    return reply


def change_sql(reply: str) -> str:
    """CHGJOB for the current job; ``reply`` is validated first."""
    return f"CALL QSYS2.QCMDEXC('CHGJOB INQMSGRPY({normalize_reply(reply)})')"


def job_info_sql(job_user: str) -> str:
    # The job user is a validated system name (no quotes possible); a table
    # function argument is written as a literal.
    return (
        "SELECT INQUIRY_MESSAGE_REPLY FROM TABLE(QSYS2.JOB_INFO("
        f"JOB_STATUS_FILTER => '*ACTIVE', JOB_USER_FILTER => '{job_user}')) X "
        "WHERE JOB_NAME = QSYS2.JOB_NAME"
    )


def read_reply(cursor) -> str:
    """The current job's INQMSGRPY; InquiryReplyError if it cannot be read."""
    cursor.execute(JOB_NAME_SQL)
    row = cursor.fetchone()
    job_name = str(row[0]).strip() if row else ""
    match = _JOB_NAME.match(job_name)
    if not match:
        raise InquiryReplyError(f"unexpected job name {job_name!r}")
    cursor.execute(job_info_sql(match.group(1)))
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise InquiryReplyError(f"job {job_name} not found in QSYS2.JOB_INFO")
    reply = str(rows[0][0] or "").strip()
    if reply not in VALID_REPLIES:
        raise InquiryReplyError(f"unexpected INQUIRY_MESSAGE_REPLY {reply!r} for job {job_name}")
    return reply


def is_alter_table(sql: str) -> bool:
    return sql.lstrip().upper().startswith("ALTER TABLE")


def cancelled_ddl_message(active_reply: str | None, suppression: str) -> str:
    """Explanation for an ALTER TABLE cancelled by CPA32B2.

    ``suppression`` says why the backend did not suppress it: one of
    NOT_IN_FIELD_CHANGE, SUPPRESSION_OFF, SUPPRESSION_UNAVAILABLE,
    SUPPRESSION_FAILED.
    """
    reasons = {
        NOT_IN_FIELD_CHANGE: (
            "The backend suppresses CPA32B2 only for the field changes of migrations and "
            "the schema editor (removing or altering a field); this statement ran outside "
            "them (RunSQL or a cursor of your own), where CPA32B2 stays a safety net."
        ),
        SUPPRESSION_OFF: (
            f"OPTIONS['{SUPPRESS_OPTION}'] is False for this database, so the backend does "
            "not suppress it; True (the default) lets migrations make such changes."
        ),
        SUPPRESSION_UNAVAILABLE: (
            "This server cannot suppress it per job (capability "
            "can_suppress_inquiry_messages is off)."
        ),
        SUPPRESSION_FAILED: (
            "The backend could not suppress it for this job (QSYS2.OVERRIDE_QAQQINI failed; "
            "the warning in the log says why)."
        ),
    }
    if active_reply == "*SYSRPYL":
        state = (
            f"This connection already uses OPTIONS['{OPTION}'] = '*SYSRPYL', so the system "
            "reply list has no entry that answers CPA32B2 with 'I'."
        )
    else:
        state = f"OPTIONS['{OPTION}'] is not set to '*SYSRPYL' for this database."
    return (
        "Db2 for i cancelled this ALTER TABLE because it may lose data (inquiry message "
        "CPA32B2, default reply C; job log CPD32CE). This happens for DROP COLUMN, for "
        "narrowing column changes and for making a column NOT NULL, also on empty "
        f"tables. {reasons[suppression]} Alternatively, an administrator allows such "
        f"changes for the whole system with a reply list entry:\n  {ADDRPYLE}\nand the "
        f"database settings set OPTIONS['{OPTION}'] = '*SYSRPYL'. {state} See {DOCS}."
    )
