"""Can the JSON functions raise an error instead of answering NULL? (phase 6)

Probe ``qtemp_json_functions`` found that ``JSON_VALUE``, ``JSON_QUERY`` and
``JSON_EXISTS`` answer invalid JSON, a value of the wrong type and a wrong path with NULL
or false, which is IBM's default. The maintainer's answer 2 on #218: use an error clause
where Django expects an error, with the exact SQLSTATE and SQLCODE from this probe, not
from IBM's documentation alone.

Writes only to QTEMP (a table that disappears with the job); reads nothing outside it.
Without commitment control (CMT=0): QTEMP tables have no journal. One connection, one
statement per case, no retries. After each error the probe checks that the connection
still answers, and stops at once if it does not. Each result says whether the error
came at prepare or at fetch, through the message.

Usage (inside the "tests" container):
    nox -s probe -- json_errors

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import _query, _step, connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

TABLE = "QTEMP.P6JERR"
GOOD = '{"a": 1, "b": "x", "c": null, "d": [10, 20], "e": {"f": true}}'
ROWS = (
    (1, GOOD),
    (2, "not json"),
    (3, "1"),
    (4, "null"),
    (5, None),
)
# Each clause in the three places it can stand, against the default as the control.
VALUE_CLAUSES = (
    "",
    "NULL ON ERROR",
    "ERROR ON ERROR",
    "ERROR ON EMPTY",
    "ERROR ON EMPTY ERROR ON ERROR",
)
EXISTS_CLAUSES = ("", "FALSE ON ERROR", "UNKNOWN ON ERROR", "TRUE ON ERROR", "ERROR ON ERROR")
# Which row, which path, what is wrong.
SITUATIONS = (
    ("a good document, a key that exists", 1, "$.a"),
    ("a good document, a missing key", 1, "$.z"),
    ("a good document, JSON null", 1, "$.c"),
    ("a good document, an object", 1, "$.e"),
    ("a good document, an array", 1, "$.d"),
    ("a good document, a negative position", 1, "$.d[-1]"),
    ("a good document, a bad path", 1, "$.a["),
    ("not JSON", 2, "$.a"),
    ("a root number, $", 3, "$"),
    ("a root null, $", 4, "$"),
    ("a SQL NULL", 5, "$.a"),
)
STRICT = (
    ("strict, a missing key", 1, "strict $.z"),
    ("lax, a missing key", 1, "lax $.z"),
    ("strict, a root number", 3, "strict $"),
    ("lax, a root number", 3, "lax $"),
    ("strict, a key of an array", 1, "strict $.d.x"),
    ("lax, a key of an array", 1, "lax $.d.x"),
)
FILTERS = (
    ("a filter on an array", "$.d[*]?(@ == 20)"),
    ("a filter on a key", "$?(@.a == 1)"),
    ("a filter, strict", "strict $.d[*]?(@ == 20)"),
    ("a filter, no match", "$.d[*]?(@ == 99)"),
)


def _checked(conn, results, key: str, sql: str, params=()) -> bool:
    """False: the connection no longer answers."""
    outcome = case(conn, results, key, sql, params)
    if outcome["result"] == "ok":
        return True
    alive = _query(conn, "SELECT 1 FROM SYSIBM.SYSDUMMY1")["result"] == "ok"
    outcome["connection_usable_after"] = alive
    return alive


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (a table gone with the job)"}
    _execute(conn, f"DROP TABLE {TABLE}")
    created = _execute(conn, f"CREATE TABLE {TABLE} (I INTEGER, C NCLOB)")
    results["create"] = created
    if created["result"] != "ok":
        return results
    for row in ROWS:
        _execute(conn, f"INSERT INTO {TABLE} VALUES (?, ?)", list(row))

    def where(row: int) -> str:
        return f"FROM {TABLE} WHERE I = {row}"

    statements: list[tuple[str, str, tuple[Any, ...]]] = []
    for name, row, path in SITUATIONS:
        for clause in VALUE_CLAUSES:
            statements.append(
                (
                    f"JSON_VALUE, {name}, {clause or 'default'}",
                    f"SELECT JSON_VALUE(C, '{path}' {clause}) {where(row)}",
                    (),
                )
            )
        for clause in ("", "ERROR ON ERROR", "ERROR ON EMPTY"):
            statements.append(
                (
                    f"JSON_QUERY, {name}, {clause or 'default'}",
                    f"SELECT JSON_QUERY(C, '{path}' WITH CONDITIONAL WRAPPER {clause}) "
                    f"{where(row)}",
                    (),
                )
            )
        for clause in EXISTS_CLAUSES:
            statements.append(
                (
                    f"JSON_EXISTS, {name}, {clause or 'default'}",
                    f"SELECT CASE WHEN JSON_EXISTS(C, '{path}' {clause}) THEN 1 ELSE 0 END "
                    f"{where(row)}",
                    (),
                )
            )
    for name, row, path in STRICT:
        for function, tail in (("JSON_VALUE", "ERROR ON ERROR"), ("JSON_QUERY", "ERROR ON ERROR")):
            statements.append(
                (
                    f"{function}, {name}",
                    f"SELECT {function}(C, '{path}' {tail}) {where(row)}",
                    (),
                )
            )
    for name, path in FILTERS:
        statements.append(
            (
                f"JSON_EXISTS, {name}, ERROR ON ERROR",
                f"SELECT CASE WHEN JSON_EXISTS(C, '{path}' ERROR ON ERROR) THEN 1 ELSE 0 END "
                f"{where(1)}",
                (),
            )
        )
    statements += [
        (
            "the wrong type, default",
            f"SELECT JSON_VALUE(C, '$.b' RETURNING INTEGER) {where(1)}",
            (),
        ),
        (
            "the wrong type, ERROR ON ERROR",
            f"SELECT JSON_VALUE(C, '$.b' RETURNING INTEGER ERROR ON ERROR) {where(1)}",
            (),
        ),
        (
            "a bad path as a marker, ERROR ON ERROR",
            f"SELECT JSON_VALUE(C, ? ERROR ON ERROR) {where(1)}",
            ("$.a[",),
        ),
        (
            "a good path as a marker, ERROR ON ERROR",
            f"SELECT JSON_VALUE(C, ? ERROR ON ERROR) {where(1)}",
            ("$.a",),
        ),
        (
            "several rows, one not JSON, ERROR ON ERROR",
            f"SELECT I, JSON_VALUE(C, '$.a' ERROR ON ERROR) FROM {TABLE} ORDER BY I",
            (),
        ),
        (
            "in WHERE, several rows, one not JSON, ERROR ON ERROR",
            f"SELECT I FROM {TABLE} WHERE JSON_VALUE(C, '$.a' RETURNING INTEGER ERROR ON ERROR) = "
            f"1",
            (),
        ),
        (
            "JSON_TABLE, ERROR ON ERROR",
            f"SELECT J.A FROM {TABLE}, JSON_TABLE(C, '$' COLUMNS(A INTEGER PATH '$.a') ERROR ON "
            f"ERROR) "
            "AS J WHERE I = 2",
            (),
        ),
        (
            "IS JSON, not JSON",
            f"SELECT CASE WHEN C IS JSON THEN 1 ELSE 0 END {where(2)}",
            (),
        ),
    ]
    for key, sql, params in statements:
        if not _checked(conn, results, key, sql, params):
            results["stopped"] = f"the connection no longer answered after: {key}"
            return results
    _execute(conn, f"DROP TABLE {TABLE}")
    return results
