"""Qualified names for objects of a table outside the current schema (#124).

``lib_other_library`` showed that a constraint or index on a table in another library
than the connection's current schema (``NAME``) needs the table's library as the
qualifier of its name. It tried ``ALTER TABLE ... ADD CONSTRAINT`` and ``CREATE INDEX``.
The schema editor writes three more forms for such a table, tried here with a table
in QTEMP, which is outside the current schema too:

1. a named constraint inside ``CREATE TABLE`` (``CONSTRAINT <name> UNIQUE (...)``,
   ``CHECK``): does an unqualified name take the table's schema, or the current one?
2. ``RENAME INDEX <qualified> TO <new>``: may the new name be qualified, must it be?
3. ``RENAME TABLE <qualified> TO <new>``: the same.

QTEMP takes no constraints (SQL7008, a constraint needs a journal), but Db2 for i
checks the name's qualifier first: an unqualified constraint name on a QTEMP table
gave SQL5051 ("Qualifier ... not same as name QTEMP"), a qualified one SQL7008
(IBMI_NOTES, "A unique constraint cannot be created in QTEMP"). So SQL5051 means "the
name went to the current schema" and SQL7008 "the name was accepted for QTEMP".

QTEMP only: every object is created with an explicit ``QTEMP.`` table name and is gone
with the job. No unqualified ``CREATE INDEX`` (that one would land in the current
schema, ``lib_other_library``). A rename changes a name in place, never the library.
A last read-only catalog check confirms that nothing named ``PQN%`` exists in the
current schema. One connection, no retries.

Usage (inside the "tests" container):
    nox -s probe -- qualified_names

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute, _rows
from qtemp_later_flags import _step

NEEDS_CONNECTION = True
AUTOCOMMIT = True


def _table(conn, results, key: str, sql: str) -> dict[str, Any]:
    outcome = _execute(conn, sql)
    _step(results, key, {"sql": sql, **outcome})
    return outcome


def _index_schema(conn, name: str) -> list:
    return _rows(
        conn,
        "SELECT INDEX_SCHEMA FROM QSYS2.SYSINDEXES WHERE INDEX_NAME = ? "
        "AND INDEX_SCHEMA IN ('QTEMP', CURRENT SCHEMA)",
        (name,),
    )


def _table_exists(conn, name: str) -> bool:
    # QTEMP objects are not in the catalog; a query on the table tells.
    return _execute(conn, f"SELECT COUNT(*) FROM QTEMP.{name}")["result"] == "ok"


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (PQN* tables and indexes, gone with the job)"}

    # 1. Named constraints inside CREATE TABLE.
    for kind, body in (("unique", "UNIQUE (N)"), ("check", "CHECK (N > 0)")):
        for form, name in (("unqualified", "PQNC"), ("qualified", "QTEMP.PQNC")):
            _execute(conn, "DROP TABLE QTEMP.PQNT")
            _table(
                conn,
                results,
                f"create table, {form} {kind} constraint",
                f"CREATE TABLE QTEMP.PQNT (ID INTEGER NOT NULL, N INTEGER, "
                f"CONSTRAINT {name} {body})",
            )
    # The control: the same table without a constraint.
    _execute(conn, "DROP TABLE QTEMP.PQNT")
    _table(
        conn,
        results,
        "create table, no constraint (control)",
        "CREATE TABLE QTEMP.PQNT (ID INTEGER NOT NULL, N INTEGER)",
    )

    # 2. RENAME INDEX, the new name unqualified and qualified.
    created = _table(
        conn, results, "create index QTEMP.PQNI1", "CREATE INDEX QTEMP.PQNI1 ON QTEMP.PQNT (N)"
    )
    if created["result"] == "ok":
        for key, sql, new in (
            ("rename index, new name unqualified", "RENAME INDEX QTEMP.PQNI1 TO PQNI2", "PQNI2"),
            (
                "rename index, new name qualified",
                "RENAME INDEX QTEMP.PQNI2 TO QTEMP.PQNI3",
                "PQNI3",
            ),
        ):
            outcome = _table(conn, results, key, sql)
            outcome["new name found in"] = _index_schema(conn, new)
        _step(results, "drop index, qualified", _execute(conn, "DROP INDEX QTEMP.PQNI3"))
        _step(
            results,
            "after the drops: PQNI* in QTEMP or the current schema",
            {"rows": [_index_schema(conn, n) for n in ("PQNI1", "PQNI2", "PQNI3")]},
        )

    # 3. RENAME TABLE, the new name unqualified and qualified.
    for key, sql, new in (
        ("rename table, new name unqualified", "RENAME TABLE QTEMP.PQNT TO PQNT2", "PQNT2"),
        ("rename table, new name qualified", "RENAME TABLE QTEMP.PQNT2 TO QTEMP.PQNT3", "PQNT3"),
    ):
        outcome = _table(conn, results, key, sql)
        outcome["new table in QTEMP"] = _table_exists(conn, new)

    for name in ("PQNT", "PQNT2", "PQNT3"):
        _execute(conn, f"DROP TABLE QTEMP.{name}")

    # Nothing in the current schema (read-only).
    _step(
        results,
        "objects named PQN% in the current schema (expected none)",
        {
            "tables": _rows(
                conn,
                "SELECT TABLE_NAME FROM QSYS2.SYSTABLES "
                "WHERE TABLE_SCHEMA = CURRENT SCHEMA AND TABLE_NAME LIKE 'PQN%'",
            ),
            "indexes": _rows(
                conn,
                "SELECT INDEX_NAME FROM QSYS2.SYSINDEXES "
                "WHERE INDEX_SCHEMA = CURRENT SCHEMA AND INDEX_NAME LIKE 'PQN%'",
            ),
            "constraints": _rows(
                conn,
                "SELECT CONSTRAINT_NAME FROM QSYS2.SYSCST "
                "WHERE CONSTRAINT_SCHEMA = CURRENT SCHEMA "
                "AND CONSTRAINT_NAME LIKE 'PQN%'",
            ),
        },
    )
    return results
