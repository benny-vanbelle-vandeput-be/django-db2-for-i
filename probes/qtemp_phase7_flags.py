"""The flags that are off "not verified on IBM i", and CHR / ASCII beyond
single-byte characters (phase 7, sections 2 and 3).

Writes only to QTEMP (a table gone with the job); reads nothing outside it but
SYSIBM.SYSDUMMY1. Without commitment control (CMT=0). One connection, no
retries. Each statement's rows, or its SQLSTATE and SQLCODE, are recorded.

- ``allows_group_by_selected_pks``: ``GROUP BY`` the primary key alone while
  selecting other columns of the same table.
- ``greatest_least_ignores_nulls``: ``GREATEST`` / ``LEAST`` (and ``MAX`` /
  ``MIN`` as scalar functions) with a NULL argument.
- ``has_case_insensitive_like``: ``'ABC' LIKE 'abc'``.
- ``has_native_json_field``, ``has_native_uuid_field``: a ``JSON`` and a
  ``UUID`` column type.
- ``supports_explaining_query_execution``: ``EXPLAIN`` forms.
- ``supports_logical_xor``: ``XOR`` in a predicate and on BOOLEAN values.
- ``supports_tablespaces``: ``CREATE TABLE ... IN <tablespace>``.
- ``supports_uuid4_function``, ``supports_uuid7_function``: ``GENERATE_UUID``,
  ``GENERATE_UUID_BINARY`` and ``GENERATE_UNIQUE``, with the version nibble of
  what they return.
- ``Chr`` / ``Ord``: ``CHR`` / ``ASCII`` above 127, and a UTF-16 conversion
  (``UX'...'``, ``INTERPRET`` of binary as ``GRAPHIC`` CCSID 1200, ``HEX`` of a
  ``GRAPHIC`` value) for a code point given as a parameter.

Usage (inside the "tests" container):
    nox -s probe -- phase7_flags

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _step, connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.P7FLAG"
DUMMY = "FROM SYSIBM.SYSDUMMY1"

# key, SQL, parameters
CASES: tuple[tuple[str, str, tuple[Any, ...]], ...] = (
    # allows_group_by_selected_pks
    (
        "group by pk: other columns selected",
        f"SELECT ID, NAME, COUNT(*) FROM {TABLE} GROUP BY ID ORDER BY ID",
        (),
    ),
    (
        "group by pk: the control (every column grouped)",
        f"SELECT ID, NAME, COUNT(*) FROM {TABLE} GROUP BY ID, NAME ORDER BY ID",
        (),
    ),
    # greatest_least_ignores_nulls
    ("greatest with NULL", f"SELECT GREATEST(1, CAST(NULL AS INTEGER), 3) {DUMMY}", ()),
    ("least with NULL", f"SELECT LEAST(1, CAST(NULL AS INTEGER), 3) {DUMMY}", ()),
    ("scalar MAX with NULL", f"SELECT MAX(1, CAST(NULL AS INTEGER), 3) {DUMMY}", ()),
    # has_case_insensitive_like
    (
        "like: 'ABC' LIKE 'abc'",
        f"SELECT CASE WHEN 'ABC' LIKE 'abc' THEN 1 ELSE 0 END {DUMMY}",
        (),
    ),
    (
        "like: a column against a lowercase pattern",
        f"SELECT COUNT(*) FROM {TABLE} WHERE NAME LIKE 'alpha%'",
        (),
    ),
    # supports_logical_xor
    (
        "xor: in a predicate",
        f"SELECT 1 {DUMMY} WHERE (1 = 1) XOR (1 = 0)",
        (),
    ),
    ("xor: BOOLEAN values", f"SELECT TRUE XOR FALSE {DUMMY}", ()),
    # supports_uuid4_function, supports_uuid7_function
    ("uuid: GENERATE_UUID()", f"SELECT GENERATE_UUID() {DUMMY}", ()),
    (
        "uuid: GENERATE_UUID() version nibble",
        f"SELECT SUBSTR(GENERATE_UUID(), 15, 1) {DUMMY}",
        (),
    ),
    ("uuid: GENERATE_UUID_BINARY()", f"SELECT HEX(GENERATE_UUID_BINARY()) {DUMMY}", ()),
    ("uuid: GENERATE_UNIQUE()", f"SELECT HEX(GENERATE_UNIQUE()) {DUMMY}", ()),
    # supports_explaining_query_execution
    ("explain: EXPLAIN PLAN FOR", f"EXPLAIN PLAN FOR SELECT 1 {DUMMY}", ()),
    ("explain: EXPLAIN SELECT", f"EXPLAIN SELECT 1 {DUMMY}", ()),
    # Chr / Ord
    ("chr: CHR(65)", f"SELECT CHR(65) {DUMMY}", ()),
    ("chr: CHR(233)", f"SELECT CHR(233), HEX(CHR(233)) {DUMMY}", ()),
    ("chr: CHR(8364)", f"SELECT CHR(8364), HEX(CHR(8364)) {DUMMY}", ()),
    ("ascii: ASCII('é')", f"SELECT ASCII(?) {DUMMY}", ("é",)),
    ("ascii: ASCII('€')", f"SELECT ASCII(?) {DUMMY}", ("€",)),
    ("utf-16: UX'00E9'", f"SELECT UX'00E9', HEX(UX'00E9') {DUMMY}", ()),
    ("utf-16: UX'20AC'", f"SELECT UX'20AC' {DUMMY}", ()),
    (
        "utf-16: INTERPRET of BX'00E9' as GRAPHIC CCSID 1200",
        f"SELECT INTERPRET(BX'00E9' AS GRAPHIC(1) CCSID 1200) {DUMMY}",
        (),
    ),
    (
        "chr via INTERPRET: 233 as a parameter",
        "SELECT INTERPRET(HEXTORAW(RIGHT(HEX(CAST(? AS INTEGER)), 4))"
        f" AS GRAPHIC(1) CCSID 1200) {DUMMY}",
        (233,),
    ),
    (
        "chr via INTERPRET: 8364 as a parameter",
        "SELECT INTERPRET(HEXTORAW(RIGHT(HEX(CAST(? AS INTEGER)), 4))"
        f" AS GRAPHIC(1) CCSID 1200) {DUMMY}",
        (8364,),
    ),
    (
        "chr via INTERPRET: 128512 (outside the BMP) as a parameter",
        "SELECT INTERPRET(HEXTORAW(RIGHT(HEX(CAST(? AS INTEGER)), 4))"
        f" AS GRAPHIC(1) CCSID 1200) {DUMMY}",
        (128512,),
    ),
    (
        "ord via HEX: 'é' as GRAPHIC CCSID 1200",
        f"SELECT HEX(CAST(? AS GRAPHIC(1) CCSID 1200)) {DUMMY}",
        ("é",),
    ),
    (
        "ord via INTERPRET: 'é' to an integer",
        "SELECT INTERPRET(BX'0000' CONCAT CAST(CAST(? AS GRAPHIC(1) CCSID 1200)"
        f" AS BINARY(2)) AS INTEGER) {DUMMY}",
        ("é",),
    ),
    (
        "ord via HEX and a lookup-free conversion: '€'",
        "SELECT HEX(CAST(? AS GRAPHIC(1) CCSID 1200)),"
        " INTERPRET(HEXTORAW('0000' CONCAT HEX(CAST(? AS GRAPHIC(1) CCSID 1200)))"
        f" AS INTEGER) {DUMMY}",
        ("€", "€"),
    ),
)

# key, DDL (each table is dropped again at once)
TYPES: tuple[tuple[str, str], ...] = (
    ("type: JSON column", "CREATE TABLE QTEMP.P7TYPE (J JSON)"),
    ("type: UUID column", "CREATE TABLE QTEMP.P7TYPE (U UUID)"),
    ("tablespace: CREATE TABLE ... IN", "CREATE TABLE QTEMP.P7TYPE (I INTEGER) IN USERSPACE1"),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    # QTEMP has no journal, so no PRIMARY KEY constraint (SQL7008): a unique
    # index on ID stands in for it in the GROUP BY case.
    created = _execute(conn, f"CREATE TABLE {TABLE} (ID INTEGER NOT NULL, NAME NVARCHAR(20))")
    if created["result"] != "ok":
        return _step(results, "create", created) and results
    _step(
        results,
        "group by pk: unique index on ID",
        _execute(conn, f"CREATE UNIQUE INDEX {TABLE}I ON {TABLE} (ID)"),
    )
    for row in ((1, "Alpha"), (2, "alpha"), (3, "Beta")):
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?)", list(row))
    for key, sql, params in CASES:
        case(conn, results, key, sql, params)
    for key, ddl in TYPES:
        _execute(conn, "DROP TABLE QTEMP.P7TYPE")
        _step(results, key, {"sql": ddl, **_execute(conn, ddl)})
        _execute(conn, "DROP TABLE QTEMP.P7TYPE")
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
