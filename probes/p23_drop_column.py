"""Probe 23: DROP COLUMN with and without CASCADE (phase 3, step B, decision 4).

Writes only to QTEMP (tables, indexes and views that disappear with the job)
and changes only the probe's own job: its inquiry message reply is set to
*DFT for the run (so CPA32B2 is answered with its default reply and the job
never waits) and set back to the value read before.

Django 5.2's schema editor writes ``ALTER TABLE t DROP COLUMN c CASCADE``,
6.0+ writes it without CASCADE. Db2 for i's DROP COLUMN takes CASCADE or
RESTRICT; which one applies when neither is given is not assumed here. For a
column with a dependent index, and one with a dependent view, each form (no
keyword, RESTRICT, CASCADE) is tried on fresh objects, and the probe records
the SQLSTATE / SQLCODE, the job log messages and whether the index and the
view still exist afterwards. A column without dependents is the control.

Limits: QTEMP tables take no constraints (SQL7008, probe 22), so constraint
dependencies (a CHECK or a foreign key on the column) are not covered here.
DROP COLUMN sends inquiry message CPA32B2 even on an empty table (probe
w08); with the default reply C the statement is cancelled (HY008), so a
form that gets past Db2 for i's dependency check ends cancelled rather than
executed. Which forms are refused over a dependency, and with which error,
is what this probe can tell.

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True
AUTOCOMMIT = True
BACKEND = {"CMT": "1", "TRUEAUTOCOMMIT": "1", "NAM": "0", "DFT": "5", "TFT": "2"}
_SQLCODE = re.compile(r"\((-?\d+)\)")
_PREFIX = re.compile(r"^(\[[^\]]*\]\s*)+")

TABLE = "QTEMP.P23T"
INDEX = "QTEMP.P23I"
VIEW = "QTEMP.P23V"
FORMS = {"no keyword": "", "RESTRICT": " RESTRICT", "CASCADE": " CASCADE"}
JOB_LOG = (
    "SELECT MESSAGE_ID FROM TABLE(QSYS2.JOBLOG_INFO('*')) X "
    "ORDER BY ORDINAL_POSITION DESC FETCH FIRST 6 ROWS ONLY"
)


def connection_attributes(settings: Settings) -> dict[str, str]:
    import pyodbc

    pyodbc.pooling = False
    return BACKEND


def _inquiry():
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from django_db2_for_i import inquiry

    return inquiry


def _execute(conn, sql: str) -> dict[str, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return {"result": "ok"}
    except pyodbc.Error as exc:
        sqlstate = str(exc.args[0]) if exc.args else ""
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        match = _SQLCODE.search(message)
        return {
            "result": "error",
            "sqlstate": sqlstate,
            "sqlcode": int(match.group(1)) if match else None,
            "message": _PREFIX.sub("", message)[:120],
        }
    finally:
        cursor.close()


def _values(conn, sql: str) -> list:
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()


def _exists(conn, sql: str) -> bool:
    return _execute(conn, sql)["result"] == "ok"


def _fresh(conn, dependent: str) -> None:
    """A new table with one row; the dependent index or view on column B."""
    for sql in (f"DROP VIEW {VIEW}", f"DROP INDEX {INDEX}", f"DROP TABLE {TABLE}"):
        _execute(conn, sql)
    for sql in (
        f"CREATE TABLE {TABLE} (A INTEGER, B INTEGER, C INTEGER)",
        f"INSERT INTO {TABLE} VALUES (1, 2, 3) WITH NC",
    ):
        outcome = _execute(conn, sql)
        if outcome["result"] != "ok":
            raise RuntimeError(f"setup failed: {sql}: {outcome}")
    if dependent == "index":
        _execute(conn, f"CREATE INDEX {INDEX} ON {TABLE} (B)")
    elif dependent == "view":
        _execute(conn, f"CREATE VIEW {VIEW} AS SELECT A, B FROM {TABLE}")


def case(conn, dependent: str, column: str, form: str) -> dict[str, Any]:
    _fresh(conn, dependent)
    outcome = _execute(conn, f"ALTER TABLE {TABLE} DROP COLUMN {column}{FORMS[form]}")
    outcome["job log"] = _values(conn, JOB_LOG)
    outcome["column still there"] = _exists(conn, f"SELECT {column} FROM {TABLE}")
    if dependent == "index":
        outcome["index still there"] = _values(
            conn, "SELECT COUNT(*) FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE', 'P23I')) X"
        ) == [1]
    if dependent == "view":
        outcome["view still there"] = _exists(conn, f"SELECT A FROM {VIEW}")
    return outcome


def run(settings: Settings, conn) -> dict[str, Any]:
    inquiry = _inquiry()
    cursor = conn.cursor()
    try:
        original = inquiry.read_reply(cursor)
    finally:
        cursor.close()
    results: dict[str, Any] = {"inquiry message reply before": original}
    changed = _execute(conn, inquiry.change_sql("*DFT"))
    results["set *DFT"] = changed
    if changed["result"] != "ok":
        print(f"  could not set INQMSGRPY(*DFT): {changed}; nothing else was run")
        return results
    try:
        for dependent, column in (("none", "C"), ("index", "B"), ("view", "B")):
            for form in FORMS:
                label = f"{dependent} dependent, DROP COLUMN {column}, {form}"
                outcome = case(conn, dependent, column, form)
                results[label] = outcome
                print(f"\n  {label}")
                for key, value in outcome.items():
                    print(f"    {key:<20} {value}")
    finally:
        for sql in (f"DROP VIEW {VIEW}", f"DROP INDEX {INDEX}", f"DROP TABLE {TABLE}"):
            _execute(conn, sql)
        restored = _execute(conn, inquiry.change_sql(original))
        results["set back"] = {"reply": original, **restored}
        print(f"\n  inquiry message reply set back to {original}: {restored['result']}")
    return results
