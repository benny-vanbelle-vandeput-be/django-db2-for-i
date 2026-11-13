"""Which system-name forms Db2 for i accepts (phase 7, section 6; answer 5).

Every table, column and index has, next to its SQL name, a system name of at
most 10 characters. The backend will set them (``FOR SYSTEM NAME`` /
``FOR COLUMN``) instead of letting IBM i generate them. This verifies each SQL
form before the backend writes it, and what Db2 for i does with conflicts:

- tables: ``CREATE TABLE <long> FOR SYSTEM NAME <sys>``; a short SQL name with a
  different system name; ``RENAME TABLE ... TO <long> FOR SYSTEM NAME <sys>``;
  a system name that is taken, too long, lowercase or delimited;
- columns: ``<long> FOR COLUMN <sys> <type>`` in ``CREATE TABLE`` and in
  ``ALTER TABLE ... ADD COLUMN``; a short column name with ``FOR COLUMN``; two
  columns with the same system name; a system name of 11 characters;
- indexes: ``CREATE INDEX <long> FOR SYSTEM NAME <sys>``; ``RENAME INDEX ... TO
  <long> FOR SYSTEM NAME <sys>``;
- access by either name (``SELECT`` through the system name), and what the
  catalogs report for QTEMP (``QSYS2.SYSTABLES``, ``SYSCOLUMNS``, ``SYSINDEXES``,
  and ``QSYS2.OBJECT_STATISTICS``, which reads the library itself).

Writes only to QTEMP (tables and indexes that disappear with the job); reads
nothing outside it but the catalog views, filtered to QTEMP. Without commitment
control (CMT=0): QTEMP tables have no journal, so no constraints either
(SQL7008). Each statement's outcome is recorded with its SQLSTATE and SQLCODE.

Usage (inside the "tests" container):
    nox -s probe -- system_names

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401

NEEDS_CONNECTION = True
AUTOCOMMIT = True

# Long SQL names (more than 10 characters) and the system names to give them.
TABLE = "PROBE_SYSTEM_NAMES_TABLE"
TABLE_SYS = "PSNTAB"
RENAMED = "PROBE_SYSTEM_NAMES_RENAMED"
RENAMED_SYS = "PSNREN"
SHORT = "PSNSHORT"
SHORT_SYS = "PSNSH2"
INDEX = "PROBE_SYSTEM_NAMES_INDEX"
INDEX_SYS = "PSNIDX"
INDEX_RENAMED = "PROBE_SYSTEM_NAMES_IDX_RENAMED"
INDEX_RENAMED_SYS = "PSNIDX2"
OBJECTS = (
    TABLE,
    TABLE_SYS,
    RENAMED,
    RENAMED_SYS,
    SHORT,
    SHORT_SYS,
    "PROBE_SYSTEM_NAMES_TAKEN",
    "PSNTAKEN",
    "PROBE_SYSTEM_NAMES_BAD",
    "PROBE_SYSTEM_NAMES_COLS",
    "PSNCOLS",
    "PSN_QUOTED_LONG_TABLE",
    "PSN_QUOTED_LONG_TABLE2",
    "PSNQT",
)
QUOTED_INDEXES = ("PSN_QUOTED_LONG_INDEX", "PSNQI", "PSN_QUOTED_UNIQUE_INDEX", "PSNQU")


def _cleanup(conn) -> None:
    for name in (INDEX, INDEX_SYS, INDEX_RENAMED, INDEX_RENAMED_SYS, *QUOTED_INDEXES):
        _execute(conn, f"DROP INDEX QTEMP.{name}")
    for name in OBJECTS:
        _execute(conn, f"DROP TABLE QTEMP.{name}")


def _catalog(conn, results, key: str) -> None:
    """What each catalog says about the probe's objects in QTEMP."""
    _step(
        results,
        f"{key}: SYSTABLES",
        _query(
            conn,
            "SELECT TABLE_NAME, SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES"
            " WHERE TABLE_SCHEMA = 'QTEMP' AND SYSTEM_TABLE_NAME LIKE 'PSN%'"
            " ORDER BY TABLE_NAME",
        ),
    )
    _step(
        results,
        f"{key}: SYSCOLUMNS",
        _query(
            conn,
            "SELECT TABLE_NAME, COLUMN_NAME, SYSTEM_COLUMN_NAME FROM QSYS2.SYSCOLUMNS"
            " WHERE TABLE_SCHEMA = 'QTEMP' AND SYSTEM_TABLE_NAME LIKE 'PSN%'"
            " ORDER BY TABLE_NAME, ORDINAL_POSITION",
        ),
    )
    _step(
        results,
        f"{key}: SYSINDEXES",
        _query(
            conn,
            "SELECT INDEX_NAME, SYSTEM_INDEX_NAME, TABLE_NAME FROM QSYS2.SYSINDEXES"
            " WHERE INDEX_SCHEMA = 'QTEMP' AND SYSTEM_INDEX_NAME LIKE 'PSN%'"
            " ORDER BY INDEX_NAME",
        ),
    )
    _step(
        results,
        f"{key}: OBJECT_STATISTICS",
        _query(
            conn,
            "SELECT OBJNAME, OBJLONGNAME, OBJATTRIBUTE"
            " FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE')) X"
            " WHERE OBJNAME LIKE 'PSN%' ORDER BY OBJNAME",
        ),
    )


def _tables(conn, results) -> None:
    ok = (
        _step(
            results,
            "table: create long name FOR SYSTEM NAME",
            _execute(
                conn,
                f"CREATE TABLE QTEMP.{TABLE} FOR SYSTEM NAME {TABLE_SYS}"
                " (ID INTEGER NOT NULL, LONG_COLUMN_NAME FOR COLUMN LONGCOL INTEGER)",
            ),
        )["result"]
        == "ok"
    )
    if ok:
        _step(
            results,
            "table: insert by SQL names",
            _execute(conn, f"INSERT INTO QTEMP.{TABLE} (ID, LONG_COLUMN_NAME) VALUES (1, 2)"),
        )
        _step(
            results,
            "table: select by system names",
            _query(conn, f"SELECT ID, LONGCOL FROM QTEMP.{TABLE_SYS}"),
        )
        _step(
            results,
            "table: select the long column by SQL name",
            _query(conn, f"SELECT LONG_COLUMN_NAME FROM QTEMP.{TABLE}"),
        )
    _step(
        results,
        "table: short SQL name with another system name",
        _execute(conn, f"CREATE TABLE QTEMP.{SHORT} FOR SYSTEM NAME {SHORT_SYS} (ID INTEGER)"),
    )
    _step(
        results,
        "table: short SQL name equal to its system name",
        _execute(conn, "CREATE TABLE QTEMP.PSNSAME FOR SYSTEM NAME PSNSAME (ID INTEGER)"),
    )
    _execute(conn, "DROP TABLE QTEMP.PSNSAME")
    _step(
        results,
        "table: system name already taken",
        _execute(
            conn,
            f"CREATE TABLE QTEMP.PROBE_SYSTEM_NAMES_TAKEN FOR SYSTEM NAME {TABLE_SYS} (ID INTEGER)",
        ),
    )
    _step(
        results,
        "table: long name whose generated system name would clash",
        _execute(conn, "CREATE TABLE QTEMP.PSNTAKEN_LONGER_NAME (ID INTEGER)"),
    )
    _execute(conn, "DROP TABLE QTEMP.PSNTAKEN_LONGER_NAME")
    for label, name in (
        ("11 characters", "PSNELEVEN01"),
        ("lowercase, undelimited", "psnlower"),
        ("delimited lowercase", '"psnlower"'),
        ("starts with a digit", "1PSN"),
        ("with an underscore", "PSN_US"),
        ("with #, @ and $", "PSN#@$"),
    ):
        outcome = _step(
            results,
            f"table: system name {label}",
            _execute(
                conn,
                f"CREATE TABLE QTEMP.PROBE_SYSTEM_NAMES_BAD FOR SYSTEM NAME {name} (ID INTEGER)",
            ),
        )
        if outcome["result"] == "ok":
            _step(
                results,
                f"table: system name {label}: as stored",
                _query(
                    conn,
                    "SELECT OBJNAME FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE')) X"
                    " WHERE OBJLONGNAME = 'PROBE_SYSTEM_NAMES_BAD'",
                ),
            )
            _execute(conn, "DROP TABLE QTEMP.PROBE_SYSTEM_NAMES_BAD")


def _columns(conn, results) -> None:
    table = "PROBE_SYSTEM_NAMES_COLS"
    _step(
        results,
        "column: two columns with the same system name",
        _execute(
            conn,
            f"CREATE TABLE QTEMP.{table} FOR SYSTEM NAME PSNCOLS"
            " (FIRST_LONG_COLUMN FOR COLUMN SAMECOL INTEGER,"
            " SECOND_LONG_COLUMN FOR COLUMN SAMECOL INTEGER)",
        ),
    )
    _execute(conn, f"DROP TABLE QTEMP.{table}")
    _step(
        results,
        "column: system name of 11 characters",
        _execute(
            conn,
            f"CREATE TABLE QTEMP.{table} FOR SYSTEM NAME PSNCOLS"
            " (LONG_COLUMN_NAME FOR COLUMN ELEVENCHARS INTEGER)",
        ),
    )
    _execute(conn, f"DROP TABLE QTEMP.{table}")
    _step(
        results,
        "column: short column name with another FOR COLUMN",
        _execute(
            conn,
            f"CREATE TABLE QTEMP.{table} FOR SYSTEM NAME PSNCOLS"
            " (SHORTCOL FOR COLUMN OTHERCOL INTEGER)",
        ),
    )
    _execute(conn, f"DROP TABLE QTEMP.{table}")
    _step(
        results,
        "column: long name without FOR COLUMN (generated system name)",
        _execute(
            conn,
            f"CREATE TABLE QTEMP.{table} FOR SYSTEM NAME PSNCOLS"
            " (FIRST_LONG_COLUMN INTEGER, FIRST_LONG_COLUMN_TWO INTEGER)",
        ),
    )
    _step(
        results,
        "column: generated system names",
        _query(
            conn,
            "SELECT COLUMN_NAME, SYSTEM_COLUMN_NAME FROM QSYS2.SYSCOLUMNS"
            " WHERE TABLE_SCHEMA = 'QTEMP' AND SYSTEM_TABLE_NAME = 'PSNCOLS'"
            " ORDER BY ORDINAL_POSITION",
        ),
    )
    _execute(conn, f"DROP TABLE QTEMP.{table}")
    _step(
        results,
        "column: ALTER TABLE ADD COLUMN with FOR COLUMN",
        _execute(
            conn,
            f"ALTER TABLE QTEMP.{TABLE} ADD COLUMN ADDED_LONG_COLUMN FOR COLUMN ADDEDCOL INTEGER",
        ),
    )
    _step(
        results,
        "column: ALTER TABLE ADD COLUMN, system name taken",
        _execute(
            conn,
            f"ALTER TABLE QTEMP.{TABLE} ADD COLUMN OTHER_LONG_COLUMN FOR COLUMN ADDEDCOL INTEGER",
        ),
    )
    _step(
        results,
        "column: select the added column by both names",
        _query(conn, f"SELECT ADDED_LONG_COLUMN, ADDEDCOL FROM QTEMP.{TABLE}"),
    )
    _step(
        results,
        "column: RENAME COLUMN (expected refused on 7.5)",
        _execute(conn, f"ALTER TABLE QTEMP.{TABLE} RENAME COLUMN ADDED_LONG_COLUMN TO NEWER_LONG"),
    )


def _indexes(conn, results) -> None:
    _step(
        results,
        "index: create long name FOR SYSTEM NAME",
        _execute(
            conn,
            f"CREATE INDEX QTEMP.{INDEX} FOR SYSTEM NAME {INDEX_SYS}"
            f" ON QTEMP.{TABLE} (LONG_COLUMN_NAME)",
        ),
    )
    _step(
        results,
        "index: create without FOR SYSTEM NAME (generated)",
        _execute(conn, f"CREATE INDEX QTEMP.PROBE_SYSTEM_NAMES_GEN_INDEX ON QTEMP.{TABLE} (ID)"),
    )
    _step(
        results,
        "index: generated system name",
        _query(
            conn,
            "SELECT OBJNAME, OBJLONGNAME FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE')) X"
            " WHERE OBJLONGNAME = 'PROBE_SYSTEM_NAMES_GEN_INDEX'",
        ),
    )
    _execute(conn, "DROP INDEX QTEMP.PROBE_SYSTEM_NAMES_GEN_INDEX")
    _step(
        results,
        "index: system name taken by a table",
        _execute(
            conn,
            f"CREATE INDEX QTEMP.PROBE_SYSTEM_NAMES_IDX_TAKEN FOR SYSTEM NAME {TABLE_SYS}"
            f" ON QTEMP.{TABLE} (ID)",
        ),
    )
    _execute(conn, "DROP INDEX QTEMP.PROBE_SYSTEM_NAMES_IDX_TAKEN")
    _step(
        results,
        "index: RENAME INDEX ... FOR SYSTEM NAME",
        _execute(
            conn,
            f"RENAME INDEX QTEMP.{INDEX} TO {INDEX_RENAMED} FOR SYSTEM NAME {INDEX_RENAMED_SYS}",
        ),
    )
    _step(
        results,
        "index: drop by system name",
        _execute(conn, f"DROP INDEX QTEMP.{INDEX_RENAMED_SYS}"),
    )


def _renames(conn, results) -> None:
    _step(
        results,
        "rename: RENAME TABLE ... TO long FOR SYSTEM NAME",
        _execute(conn, f"RENAME TABLE QTEMP.{TABLE} TO {RENAMED} FOR SYSTEM NAME {RENAMED_SYS}"),
    )
    _step(
        results,
        "rename: select by the new system name",
        _query(conn, f"SELECT ID, LONGCOL FROM QTEMP.{RENAMED_SYS}"),
    )
    _step(
        results,
        "rename: RENAME TABLE ... TO long (no system name): what it becomes",
        _execute(conn, f"RENAME TABLE QTEMP.{RENAMED} TO PROBE_SYSTEM_NAMES_TABLE_AGAIN"),
    )
    _step(
        results,
        "rename: system name after a rename without one",
        _query(
            conn,
            "SELECT OBJNAME, OBJLONGNAME FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE')) X"
            " WHERE OBJLONGNAME = 'PROBE_SYSTEM_NAMES_TABLE_AGAIN'",
        ),
    )
    _step(
        results,
        "rename: RENAME TABLE ... TO short SQL name equal to a new system name",
        _execute(conn, "RENAME TABLE QTEMP.PROBE_SYSTEM_NAMES_TABLE_AGAIN TO PSNBACK"),
    )
    _step(
        results,
        "rename: names after a rename to a short name",
        _query(
            conn,
            "SELECT OBJNAME, OBJLONGNAME FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE')) X"
            " WHERE OBJNAME = 'PSNBACK' OR OBJLONGNAME = 'PSNBACK'",
        ),
    )
    _execute(conn, "DROP TABLE QTEMP.PSNBACK")


def _objects(conn, results, key: str) -> None:
    """The *FILE objects of the quoted table: does a constraint make one?"""
    _step(
        results,
        key,
        _query(
            conn,
            "SELECT OBJNAME, OBJLONGNAME, OBJATTRIBUTE"
            " FROM TABLE(QSYS2.OBJECT_STATISTICS('QTEMP', '*FILE')) X"
            " WHERE OBJLONGNAME LIKE 'PSN_QUOTED%' OR OBJNAME LIKE 'PSNQ%' ORDER BY OBJNAME",
        ),
    )


def _backend_forms(conn, results) -> None:
    """The forms the backend writes: quoted SQL names; constraints and *FILE objects."""
    table = 'QTEMP."PSN_QUOTED_LONG_TABLE"'
    _step(
        results,
        "backend: CREATE TABLE quoted FOR SYSTEM NAME, with UNIQUE and PRIMARY KEY",
        _execute(
            conn,
            f'CREATE TABLE {table} FOR SYSTEM NAME PSNQT ("ID" INTEGER NOT NULL,'
            ' "NAME" VARCHAR(10), "CODE" VARCHAR(10),'
            ' CONSTRAINT QTEMP."PSN_QUOTED_LONG_TABLE_PK" PRIMARY KEY ("ID"),'
            ' CONSTRAINT QTEMP."PSN_QUOTED_LONG_TABLE_NAME_UNIQ" UNIQUE ("NAME"))',
        ),
    )
    # Constraints need a journal; QTEMP has none (SQL7008). Without them:
    _step(
        results,
        "backend: CREATE TABLE quoted FOR SYSTEM NAME",
        _execute(
            conn,
            f'CREATE TABLE {table} FOR SYSTEM NAME PSNQT ("ID" INTEGER NOT NULL,'
            ' "NAME" VARCHAR(10), "CODE" VARCHAR(10))',
        ),
    )
    _objects(conn, results, "backend: *FILE objects after CREATE TABLE")
    _step(
        results,
        "backend: CREATE INDEX quoted FOR SYSTEM NAME",
        _execute(
            conn,
            'CREATE INDEX QTEMP."PSN_QUOTED_LONG_INDEX" FOR SYSTEM NAME PSNQI'
            f' ON {table} ("NAME" DESC)',
        ),
    )
    _step(
        results,
        "backend: CREATE UNIQUE INDEX quoted FOR SYSTEM NAME",
        _execute(
            conn,
            'CREATE UNIQUE INDEX QTEMP."PSN_QUOTED_UNIQUE_INDEX" FOR SYSTEM NAME PSNQU'
            f' ON {table} ("CODE", "ID")',
        ),
    )
    _objects(conn, results, "backend: *FILE objects after the indexes")
    _step(
        results,
        "backend: DROP INDEX by the SQL name",
        _execute(conn, 'DROP INDEX QTEMP."PSN_QUOTED_LONG_INDEX"'),
    )
    _step(
        results,
        "backend: RENAME TABLE quoted, keeping the system name",
        _execute(conn, f'RENAME TABLE {table} TO "PSN_QUOTED_LONG_TABLE2"'),
    )
    _objects(conn, results, "backend: *FILE objects after RENAME TABLE")
    _execute(conn, 'RENAME TABLE QTEMP."PSN_QUOTED_LONG_TABLE2" TO "PSN_QUOTED_LONG_TABLE"')


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables and indexes gone with the job)"}
    _cleanup(conn)
    try:
        for part in (_tables, _columns, _indexes, _backend_forms):
            print(f" -- {part.__name__.strip('_')}")
            part(conn, results)
        print(" -- catalog")
        _catalog(conn, results, "catalog")
        print(" -- renames")
        _renames(conn, results)
    finally:
        _cleanup(conn)
    return results
