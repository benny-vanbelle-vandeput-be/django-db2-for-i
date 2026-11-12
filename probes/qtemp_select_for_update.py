"""The syntax of row locks, for phase 6 (``has_select_for_update`` and its flags).

Writes only to QTEMP (tables that disappear with the job); reads nothing outside
it. Without commitment control (CMT=0): QTEMP tables have no journal. One
connection, no retries.

**This shows which statements Db2 for i accepts, not what they lock.** Whether a
second job waits or skips needs two connections, which PUB400 does not allow, and
commitment control, which QTEMP does not have. Django's own ``select_for_update``
tests use a second connection for the same reason (phase 6, open questions).

Usage (inside the "tests" container):
    nox -s probe -- select_for_update

Findings go to docs/IBMI_NOTES.md.
"""

from __future__ import annotations

from typing import Any

from _common import Settings
from qtemp_alter_table import _execute
from qtemp_later_flags import connection_attributes  # noqa: F401
from qtemp_window import case

NEEDS_CONNECTION = True
AUTOCOMMIT = True

A = "QTEMP.P6LOCKA"
B = "QTEMP.P6LOCKB"

CASES = (
    ("plain", f"SELECT I FROM {A} FOR UPDATE"),
    ("OF a column", f"SELECT I, V FROM {A} FOR UPDATE OF V"),
    ("OF a qualified column", f"SELECT T.I FROM {A} T FOR UPDATE OF T.V"),
    ("OF the key column", f"SELECT I FROM {A} FOR UPDATE OF I"),
    ("WHERE", f"SELECT I FROM {A} WHERE I = 1 FOR UPDATE"),
    ("ORDER BY", f"SELECT I FROM {A} ORDER BY I FOR UPDATE"),
    ("FETCH FIRST", f"SELECT I FROM {A} FETCH FIRST 1 ROWS ONLY FOR UPDATE"),
    ("ORDER BY, FETCH FIRST", f"SELECT I FROM {A} ORDER BY I FETCH FIRST 1 ROWS ONLY FOR UPDATE"),
    ("OFFSET", f"SELECT I FROM {A} ORDER BY I OFFSET 1 ROWS FETCH FIRST 1 ROWS ONLY FOR UPDATE"),
    ("a join", f"SELECT A.I FROM {A} A JOIN {B} B ON A.I = B.I FOR UPDATE"),
    (
        "a join, OF the first table",
        f"SELECT A.I FROM {A} A JOIN {B} B ON A.I = B.I FOR UPDATE OF V",
    ),
    ("a subquery in WHERE", f"SELECT I FROM {A} WHERE I IN (SELECT I FROM {B}) FOR UPDATE"),
    ("a subquery in FROM", f"SELECT I FROM (SELECT I FROM {A}) X FOR UPDATE"),
    ("DISTINCT", f"SELECT DISTINCT I FROM {A} FOR UPDATE"),
    ("GROUP BY", f"SELECT I, COUNT(*) FROM {A} GROUP BY I FOR UPDATE"),
    ("UNION", f"SELECT I FROM {A} UNION SELECT I FROM {B} FOR UPDATE"),
    ("WITH RS", f"SELECT I FROM {A} FOR UPDATE WITH RS"),
    (
        "WITH RS USE AND KEEP EXCLUSIVE LOCKS",
        f"SELECT I FROM {A} WITH RS USE AND KEEP EXCLUSIVE LOCKS",
    ),
    (
        "WITH RR USE AND KEEP EXCLUSIVE LOCKS",
        f"SELECT I FROM {A} WITH RR USE AND KEEP EXCLUSIVE LOCKS",
    ),
    (
        "a join, USE AND KEEP",
        f"SELECT A.I FROM {A} A JOIN {B} B ON A.I = B.I WITH RS USE AND KEEP EXCLUSIVE LOCKS",
    ),
    (
        "FETCH FIRST, USE AND KEEP",
        f"SELECT I FROM {A} FETCH FIRST 1 ROWS ONLY WITH RS USE AND KEEP EXCLUSIVE LOCKS",
    ),
    ("SKIP LOCKED DATA", f"SELECT I FROM {A} FOR UPDATE SKIP LOCKED DATA"),
    ("SKIP LOCKED DATA without FOR UPDATE", f"SELECT I FROM {A} SKIP LOCKED DATA"),
    ("WITH CS SKIP LOCKED DATA", f"SELECT I FROM {A} WITH CS SKIP LOCKED DATA"),
    ("SKIP LOCKED", f"SELECT I FROM {A} FOR UPDATE SKIP LOCKED"),
    # Phase 7: the exact forms the backend would write (FOR UPDATE ... WITH RS).
    ("WITH RS SKIP LOCKED DATA", f"SELECT I FROM {A} FOR UPDATE WITH RS SKIP LOCKED DATA"),
    ("OF a column, WITH RS", f"SELECT I, V FROM {A} FOR UPDATE OF V WITH RS"),
    (
        "OF a column, WITH RS SKIP LOCKED DATA",
        f"SELECT I, V FROM {A} FOR UPDATE OF V WITH RS SKIP LOCKED DATA",
    ),
    (
        "ORDER BY, OFFSET, FETCH FIRST, WITH RS",
        f"SELECT I FROM {A} ORDER BY I OFFSET 1 ROWS FETCH FIRST 1 ROWS ONLY FOR UPDATE WITH RS",
    ),
    (
        "a subquery in WHERE, WITH RS",
        f"SELECT I FROM {A} WHERE I IN (SELECT I FROM {B}) FOR UPDATE WITH RS",
    ),
    (
        "a join, USE AND KEEP, SKIP LOCKED DATA",
        f"SELECT A.I FROM {A} A JOIN {B} B ON A.I = B.I"
        " WITH RS USE AND KEEP EXCLUSIVE LOCKS SKIP LOCKED DATA",
    ),
    (
        "USE AND KEEP, SKIP LOCKED DATA",
        f"SELECT I FROM {A} WITH RS USE AND KEEP EXCLUSIVE LOCKS SKIP LOCKED DATA",
    ),
    (
        "a parameter marker, WITH RS",
        f"SELECT I FROM {A} WHERE I = CAST(1 AS INTEGER) FOR UPDATE WITH RS",
    ),
    ("WAIT FOR OUTCOME", f"SELECT I FROM {A} WAIT FOR OUTCOME"),
    ("NOWAIT", f"SELECT I FROM {A} FOR UPDATE NOWAIT"),
    ("WAIT 0", f"SELECT I FROM {A} FOR UPDATE WAIT 0"),
)


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {"scope": "QTEMP only (tables gone with the job)"}
    for table in (A, B):
        _execute(conn, f"DROP TABLE {table}")
        _execute(conn, f"CREATE TABLE {table} (I INTEGER, V INTEGER)")
        _execute(conn, f"INSERT INTO {table} VALUES (1, 1), (2, 2)")
    for key, sql in CASES:
        case(conn, results, key, sql)
    for table in (A, B):
        _execute(conn, f"DROP TABLE {table}")
    return results
