"""Does the QAQQINI option SUPPRESS_INQUIRY_MESSAGES, set for the probe's own
job with QSYS2.OVERRIDE_QAQQINI, let ALTER TABLE run without CPA32B2?

Writes only to QTEMP (three one-row tables and the job's QAQQINI copy that
OVERRIDE_QAQQINI(1) creates there, all gone with the job) and changes only
the probe's own job's query options; OVERRIDE_QAQQINI(3) discards the copy
in a ``finally``. It changes no job attribute: like probe 24
(qtemp_alter_table) it runs only when the job's inquiry message reply is
*RQD, so a statement that still sends CPA32B2 is cancelled (HY008) and the
job never waits. No library, no system object, no reply list entry is
changed; the libraries outside QTEMP are only read, before and after, to
show that nothing was created there.

IBM documents the option in the QAQQINI query options table (IBM i 7.5 and
7.6): SUPPRESS_INQUIRY_MESSAGES, *DEFAULT (= *NO), *YES "System inquiry
message CPA32B2 will not be issued when altering a table", *NO. 7.5 and 7.6
have it in the base release (Db2 for i DBE enhancements: 7.4 SF99704 level
4, 7.3 SF99703 level 16). OVERRIDE_QAQQINI: 7.5 and 7.6 base, 7.4 SF99704
level 7; "For most QAQQINI options, none [authority] is required."

Probe w08 (qtemp_inquiry) listed the 49 rows of the QTEMP copy and found no
such option. The row may simply be absent (an absent option has its default
value): OVERRIDE_QAQQINI(2) may add it, or refuse it; both are results. If
it refuses, an INSERT into QTEMP.QAQQINI (the job's own copy in QTEMP) is
tried as a fallback.

Steps:
0. the job's own special authorities and group profile (read-only);
a. baseline: DROP COLUMN, a narrowing SET DATA TYPE and SET NOT NULL, each
   on its own one-row QTEMP table (expected: HY008, CPD32CE in the job log);
b. the QAQQINI files before the override (QTEMP, QUSRSYS, QSYS template
   row) and the objects of the two .env libraries;
c. OVERRIDE_QAQQINI(1), then (2, 'SUPPRESS_INQUIRY_MESSAGES', '*YES'), and
   the row read back;
d. the three ALTERs again, then (override only) four changes whose data
   does not fit: INTEGER -> SMALLINT with 100000, VARCHAR(10) -> VARCHAR(3)
   with 'abcdef', DECIMAL(9, 4) -> DECIMAL(9, 2) with 1.2345, SET NOT NULL
   with a NULL row; each with the rows afterwards;
e. where the QAQQINI copy lives, and the libraries compared with step b;
g. the rows of the copy whose value is not *DEFAULT (side effects);
f. OVERRIDE_QAQQINI(3) (always, in ``finally``), then the baseline again.

Usage (inside the "tests" container):
    nox -s probe -- qaqqini_inquiry

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import BACKEND, _execute, _inquiry, _rows

NEEDS_CONNECTION = True
AUTOCOMMIT = True

OPTION = "SUPPRESS_INQUIRY_MESSAGES"
JOB_LOG = (
    "SELECT MESSAGE_ID FROM TABLE(QSYS2.JOBLOG_INFO('*')) X "
    "ORDER BY ORDINAL_POSITION DESC FETCH FIRST 6 ROWS ONLY"
)
# (label, table, columns, row, statement, check that shows the change was made)
ALTERS = [
    (
        "DROP COLUMN",
        "QTEMP.PQIDROP",
        "A INTEGER, B INTEGER",
        "1, 2",
        "ALTER TABLE {t} DROP COLUMN B",
        # Fails once B is gone.
        "SELECT B FROM {t}",
    ),
    (
        "SET DATA TYPE INTEGER -> SMALLINT (narrowing, value fits)",
        "QTEMP.PQITYPE",
        "A INTEGER, B INTEGER",
        "1, 2",
        "ALTER TABLE {t} ALTER COLUMN B SET DATA TYPE SMALLINT",
        # Fails once B is SMALLINT.
        "INSERT INTO {t} VALUES (2, 100000) WITH NC",
    ),
    (
        "SET NOT NULL (no NULLs)",
        "QTEMP.PQINN",
        "A INTEGER, B INTEGER",
        "1, 2",
        "ALTER TABLE {t} ALTER COLUMN B SET NOT NULL",
        # Fails once B is NOT NULL.
        "INSERT INTO {t} VALUES (2, NULL) WITH NC",
    ),
]
# With the override only: changes whose data does not fit. Does Db2 for i
# refuse them (an error), or change the data silently?
# (label, table, columns, rows, statement)
LOSSY = [
    (
        "SET DATA TYPE INTEGER -> SMALLINT, a value does not fit",
        "QTEMP.PQILINT",
        "A INTEGER, B INTEGER",
        ["1, 2", "2, 100000"],
        "ALTER TABLE {t} ALTER COLUMN B SET DATA TYPE SMALLINT",
    ),
    (
        "SET DATA TYPE VARCHAR(10) -> VARCHAR(3), a value is longer",
        "QTEMP.PQILCHR",
        "A INTEGER, B VARCHAR(10)",
        ["1, 'abc'", "2, 'abcdef'"],
        "ALTER TABLE {t} ALTER COLUMN B SET DATA TYPE VARCHAR(3)",
    ),
    (
        "SET DATA TYPE DECIMAL(9, 4) -> DECIMAL(9, 2), a value has 4 decimals",
        "QTEMP.PQILDEC",
        "A INTEGER, B DECIMAL(9, 4)",
        ["1, 1.5", "2, 1.2345"],
        "ALTER TABLE {t} ALTER COLUMN B SET DATA TYPE DECIMAL(9, 2)",
    ),
    (
        "SET NOT NULL, a row has NULL",
        "QTEMP.PQILNUL",
        "A INTEGER, B INTEGER",
        ["1, 2", "2, NULL"],
        "ALTER TABLE {t} ALTER COLUMN B SET NOT NULL",
    ),
]
OPTION_ROW = "SELECT QQPARM, QQVAL FROM {lib}.QAQQINI WHERE QQPARM = ?"
QAQQINI_FILE = (
    "SELECT OBJNAME, OBJTYPE, OBJCREATED "
    "FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*FILE', 'QAQQINI')) X"
)
LIBRARY_OBJECTS = "SELECT OBJNAME, OBJTYPE FROM TABLE(QSYS2.OBJECT_STATISTICS(?, '*ALL')) X"


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _alter(conn, table: str, columns: str, row: str, sql: str, check: str):
    """A fresh one-row table, the ALTER, the job log and whether it took effect."""
    _execute(conn, f"DROP TABLE {table}")
    setup = [
        _execute(conn, f"CREATE TABLE {table} ({columns})"),
        _execute(conn, f"INSERT INTO {table} VALUES ({row}) WITH NC"),
    ]
    if any(step["result"] != "ok" for step in setup):
        return {"result": "setup failed", "setup": setup}
    outcome = _execute(conn, sql.format(t=table))
    outcome["job log"] = [r[0] for r in _rows(conn, JOB_LOG)]
    # The check statement fails when the ALTER took effect.
    outcome["took effect"] = _execute(conn, check.format(t=table))["result"] != "ok"
    _execute(conn, f"DROP TABLE {table}")
    return outcome


def _lossy(conn, table: str, columns: str, rows: list[str], sql: str) -> dict[str, Any]:
    """The ALTER on rows that do not fit, and the rows afterwards."""
    _execute(conn, f"DROP TABLE {table}")
    setup = [_execute(conn, f"CREATE TABLE {table} ({columns})")]
    setup += [_execute(conn, f"INSERT INTO {table} VALUES ({row}) WITH NC") for row in rows]
    if any(step["result"] != "ok" for step in setup):
        return {"result": "setup failed", "setup": setup}
    outcome = _execute(conn, sql.format(t=table))
    outcome["job log"] = [r[0] for r in _rows(conn, JOB_LOG)]
    outcome["rows after"] = [
        [str(v) for v in row] for row in _rows(conn, f"SELECT A, B FROM {table} ORDER BY A")
    ]
    _execute(conn, f"DROP TABLE {table}")
    return outcome


def lossy(conn) -> dict[str, Any]:
    results = {}
    for label, table, columns, rows, sql in LOSSY:
        results[label] = outcome = _lossy(conn, table, columns, rows, sql)
        print(f"\n  override, data does not fit: {label}")
        for key, value in outcome.items():
            print(f"    {key:<12} {value}")
    return results


def alters(conn, phase: str) -> dict[str, Any]:
    results = {}
    for label, table, columns, row, sql, check in ALTERS:
        results[label] = outcome = _alter(conn, table, columns, row, sql, check)
        print(f"\n  {phase}: {label}")
        for key, value in outcome.items():
            print(f"    {key:<12} {value}")
    return results


def qaqqini_files(conn) -> dict[str, Any]:
    """The QAQQINI files the job could see, and their SUPPRESS_INQUIRY_MESSAGES row."""
    found: dict[str, Any] = {}
    for lib in ("QTEMP", "QUSRSYS", "QSYS"):
        found[lib] = {
            "file": _rows(conn, QAQQINI_FILE, (lib,)),
            "option row": _rows(conn, OPTION_ROW.format(lib=lib), (OPTION,)),
        }
    return found


def library_objects(settings: Settings, conn) -> dict[str, list[str]]:
    """Every object of the two .env libraries and QTEMP, as 'NAME TYPE'."""
    configured = (settings.default_library, settings.other_library)
    objects: dict[str, list[str]] = {}
    for lib in ["QTEMP"] + [name for name in configured if name]:
        rows = _rows(conn, LIBRARY_OBJECTS, (lib,))
        objects[lib] = sorted(" ".join(str(v).strip() for v in row) for row in rows)
    return objects


def compare(before: dict[str, list[str]], after: dict[str, list[str]]) -> dict[str, Any]:
    return {
        lib: {
            "added": sorted(set(after.get(lib, [])) - set(before[lib])),
            "removed": sorted(set(before[lib]) - set(after.get(lib, []))),
        }
        for lib in before
    }


def run(settings: Settings, conn) -> dict[str, Any]:
    inquiry = _inquiry()
    cursor = conn.cursor()
    try:
        reply = inquiry.read_reply(cursor)
    finally:
        cursor.close()
    results: dict[str, Any] = {"inquiry message reply": reply}
    # The job's own special authorities (the procedure needs none for this option).
    results["special authorities"] = authorities = _rows(
        conn,
        "SELECT SPECIAL_AUTHORITIES, GROUP_PROFILE_NAME FROM QSYS2.USER_INFO "
        "WHERE AUTHORIZATION_NAME = CURRENT USER",
    )
    print(f"  special authorities, group profile: {authorities}")
    if reply != "*RQD":
        print(f"  the job's inquiry message reply is {reply}, not *RQD; nothing was run")
        return results

    print("\n======== a. Baseline without the override ========")
    results["a. baseline"] = alters(conn, "baseline")

    print("\n======== b. Before the override ========")
    results["b. QAQQINI files before"] = before_files = qaqqini_files(conn)
    print(f"  {before_files}")
    before = library_objects(settings, conn)
    results["b. objects before (counts)"] = {lib: len(names) for lib, names in before.items()}

    print("\n======== c. OVERRIDE_QAQQINI ========")
    created = _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(1, '', '')")
    results["c. OVERRIDE_QAQQINI(1)"] = created
    print(f"  OVERRIDE_QAQQINI(1): {created}")
    try:
        if created["result"] == "ok":
            option_set = _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(2, ?, ?)", (OPTION, "*YES"))
            results["c. OVERRIDE_QAQQINI(2)"] = option_set
            print(f"  OVERRIDE_QAQQINI(2, {OPTION}, *YES): {option_set}")
            row = _rows(conn, OPTION_ROW.format(lib="QTEMP"), (OPTION,))
            if option_set["result"] != "ok" or not row:
                # Fallback: the row in the job's own QTEMP copy.
                inserted = _execute(
                    conn,
                    "INSERT INTO QTEMP.QAQQINI (QQPARM, QQVAL) VALUES (?, ?)",
                    (OPTION, "*YES"),
                )
                results["c. fallback INSERT into QTEMP.QAQQINI"] = inserted
                print(f"  fallback INSERT: {inserted}")
                row = _rows(conn, OPTION_ROW.format(lib="QTEMP"), (OPTION,))
            results["c. option row read back"] = row
            print(f"  option row read back: {row}")

            print("\n======== d. The ALTERs with the override ========")
            results["d. with the override"] = alters(conn, "override")
            results["d. with the override, data does not fit"] = lossy(conn)

            print("\n======== e. Where the copy lives; nothing outside QTEMP ========")
            results["e. QAQQINI files with the override"] = qaqqini_files(conn)
            results["e. objects compared"] = diff = compare(before, library_objects(settings, conn))
            print(f"  {results['e. QAQQINI files with the override']}\n  {diff}")

            print("\n======== g. Rows of the copy not at *DEFAULT ========")
            results["g. non-default rows"] = non_default = _rows(
                conn,
                "SELECT VARCHAR(QQPARM, 60), VARCHAR(QQVAL, 60) FROM QTEMP.QAQQINI "
                "WHERE QQVAL <> '*DEFAULT' ORDER BY QQPARM",
            )
            results["g. row count"] = _rows(conn, "SELECT COUNT(*) FROM QTEMP.QAQQINI")
            for parm, value in non_default:
                print(f"    {str(parm).strip():<45} {str(value).strip()}")
    finally:
        discarded = _execute(conn, "CALL QSYS2.OVERRIDE_QAQQINI(3, '', '')")
        results["f. OVERRIDE_QAQQINI(3)"] = discarded
        print(f"\n  OVERRIDE_QAQQINI(3): {discarded}")

    print("\n======== f. After the discard ========")
    results["f. QAQQINI files after"] = qaqqini_files(conn)
    results["f. objects compared"] = compare(before, library_objects(settings, conn))
    results["f. baseline again"] = alters(conn, "after discard")
    return results
