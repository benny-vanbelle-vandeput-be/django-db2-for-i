"""How unique indexes treat NULLs (phase 5, step 0).

Writes only to QTEMP (tables and indexes that disappear with the job); reads
nothing outside it. Without commitment control (CMT=0): QTEMP tables have no
journal. QTEMP refuses constraints (SQL7008, probe 22), so this probe covers
unique *indexes*; the same questions for a unique *constraint* are tried once
here (to record the refusal) and need a ``lib_`` probe in the journaled test
library, only with the maintainer's approval (phase 5 plan, answer c).

- ``supports_nullable_unique_constraints``: one and several NULLs in a
  nullable unique column.
- ``supports_partially_nullable_unique_constraints``: two-column keys with
  one column NULL, the same non-NULL part twice.
- ``supports_nulls_distinct_unique_constraints``: ``NULLS DISTINCT`` /
  ``NULLS NOT DISTINCT`` on an index and a constraint, and Db2 for i's own
  ``UNIQUE WHERE NOT NULL`` index.

Usage (inside the "tests" container):
    nox -s probe -- unique_nulls

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.PUNQ"
CREATE = f"CREATE TABLE {TABLE} (A INTEGER, B INTEGER)"

INDEX_FORMS = {
    "UNIQUE INDEX (A)": "CREATE UNIQUE INDEX QTEMP.PUNQ1 ON QTEMP.PUNQ (A)",
    "UNIQUE WHERE NOT NULL INDEX (A)": (
        "CREATE UNIQUE WHERE NOT NULL INDEX QTEMP.PUNQ1 ON QTEMP.PUNQ (A)"
    ),
    "UNIQUE INDEX (A) NULLS DISTINCT": (
        "CREATE UNIQUE INDEX QTEMP.PUNQ1 ON QTEMP.PUNQ (A) NULLS DISTINCT"
    ),
    "UNIQUE INDEX (A) NULLS NOT DISTINCT": (
        "CREATE UNIQUE INDEX QTEMP.PUNQ1 ON QTEMP.PUNQ (A) NULLS NOT DISTINCT"
    ),
    "UNIQUE INDEX (A) WHERE A IS NOT NULL": (
        "CREATE UNIQUE INDEX QTEMP.PUNQ1 ON QTEMP.PUNQ (A) WHERE A IS NOT NULL"
    ),
}

TWO_COLUMN_FORMS = {
    "UNIQUE INDEX (A, B)": "CREATE UNIQUE INDEX QTEMP.PUNQ2 ON QTEMP.PUNQ (A, B)",
    "UNIQUE WHERE NOT NULL INDEX (A, B)": (
        "CREATE UNIQUE WHERE NOT NULL INDEX QTEMP.PUNQ2 ON QTEMP.PUNQ (A, B)"
    ),
}

CONSTRAINT_FORMS = {
    "UNIQUE constraint in CREATE TABLE": "CREATE TABLE QTEMP.PUNQC (A INTEGER UNIQUE)",
    "UNIQUE constraint NULLS NOT DISTINCT in CREATE TABLE": (
        "CREATE TABLE QTEMP.PUNQC (A INTEGER, "
        "CONSTRAINT QTEMP.PUNQCC UNIQUE NULLS NOT DISTINCT (A))"
    ),
}


def _nulls(conn, results, label: str, sql: str) -> None:
    _execute(conn, f"DELETE FROM {TABLE}")
    if _step(results, f"{label}: create", _execute(conn, sql))["result"] != "ok":
        return
    _step(results, f"{label}: one NULL", _execute(conn, f"INSERT INTO {TABLE} (A) VALUES (NULL)"))
    _step(
        results, f"{label}: a second NULL", _execute(conn, f"INSERT INTO {TABLE} (A) VALUES (NULL)")
    )
    _step(results, f"{label}: A=1", _execute(conn, f"INSERT INTO {TABLE} (A) VALUES (1)"))
    _step(
        results,
        f"{label}: A=1 again (duplicate)",
        _execute(conn, f"INSERT INTO {TABLE} (A) VALUES (1)"),
    )
    _execute(conn, "DROP INDEX QTEMP.PUNQ1")


def _partial_nulls(conn, results, label: str, sql: str) -> None:
    _execute(conn, f"DELETE FROM {TABLE}")
    if _step(results, f"{label}: create", _execute(conn, sql))["result"] != "ok":
        return
    _step(
        results,
        f"{label}: (1, NULL)",
        _execute(conn, f"INSERT INTO {TABLE} (A, B) VALUES (1, NULL)"),
    )
    _step(
        results,
        f"{label}: (1, NULL) again",
        _execute(conn, f"INSERT INTO {TABLE} (A, B) VALUES (1, NULL)"),
    )
    _step(
        results,
        f"{label}: (NULL, NULL) twice",
        _execute(conn, f"INSERT INTO {TABLE} (A, B) VALUES (NULL, NULL), (NULL, NULL)"),
    )
    _step(results, f"{label}: (1, 2)", _execute(conn, f"INSERT INTO {TABLE} (A, B) VALUES (1, 2)"))
    _step(
        results,
        f"{label}: (1, 2) again (duplicate)",
        _execute(conn, f"INSERT INTO {TABLE} (A, B) VALUES (1, 2)"),
    )
    _execute(conn, "DROP INDEX QTEMP.PUNQ2")


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables and indexes gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    if _step(results, "create", _execute(conn, CREATE))["result"] != "ok":
        return results
    print(" -- one column")
    for label, sql in INDEX_FORMS.items():
        _nulls(conn, results, label, sql)
    print(" -- two columns")
    for label, sql in TWO_COLUMN_FORMS.items():
        _partial_nulls(conn, results, label, sql)
    print(" -- constraints (expected SQL7008 in QTEMP)")
    for label, sql in CONSTRAINT_FORMS.items():
        _execute(conn, "DROP TABLE QTEMP.PUNQC")
        _step(results, label, _execute(conn, sql))
    _execute(conn, "DROP TABLE QTEMP.PUNQC")
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
