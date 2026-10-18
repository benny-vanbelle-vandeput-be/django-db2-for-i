"""Probe 09: SQL features behind phase 2's Django feature flags (queries).

Read-only: SELECT / VALUES on SYSIBM.SYSDUMMY1 and derived tables only.
Each check runs one statement and records the value (and Python type) or
the SQLCODE when Db2 for i rejects it. One line per check; findings go to
docs/IBMI_NOTES.md.

Areas: compound queries (UNION / INTERSECT / EXCEPT, ordering and slicing
inside the parts), subqueries (sliced IN, GROUP BY), boolean predicates in
the select list, NULL ordering, the parameter marker limit, regular
expressions, integer arithmetic and bit functions, CONCAT and LIKE ESCAPE,
LOB (NCLOB) values in ORDER BY / GROUP BY / DISTINCT / comparisons,
aggregate functions, timestamp subtraction.
"""

from __future__ import annotations

import re
from typing import Any

from _common import Settings

NEEDS_CONNECTION = True

D = "FROM SYSIBM.SYSDUMMY1"
V3 = "(VALUES 3, 1, 2) T (X)"
VN = "(VALUES CAST(1 AS INTEGER), CAST(NULL AS INTEGER), CAST(2 AS INTEGER)) T (X)"
LOB = (
    "(VALUES (1, CAST('b' AS NCLOB(1K))), (2, CAST('a' AS NCLOB(1K))), "
    "(3, CAST('b' AS NCLOB(1K)))) T (K, L)"
)
# A stored DBCLOB column; the filter keeps the result empty (the statement
# still compiles, which is what the LOB checks need).
PKG = "QSYS2.SYSPACKAGESTMTSTAT WHERE PACKAGE_SCHEMA = 'NOSUCHLIB'"
# A UNION that refers to the outer query's T.X (correlated).
CORRELATED_UNION = "SELECT T.X AS Y FROM SYSIBM.SYSDUMMY1 UNION SELECT 9 AS Y FROM SYSIBM.SYSDUMMY1"
_SQLCODE = re.compile(r"\((-\d+)\)")

# (area, label, sql, params, expected rows or None to only record)
CHECKS: list[tuple[str, str, str, tuple, Any]] = [
    # --- compound queries
    ("compound", "UNION", f"SELECT 1 {D} UNION SELECT 2 {D} ORDER BY 1", (), [(1,), (2,)]),
    ("compound", "UNION ALL", f"SELECT 1 {D} UNION ALL SELECT 1 {D}", (), [(1,), (1,)]),
    ("compound", "INTERSECT", f"SELECT X FROM {V3} INTERSECT SELECT 2 {D}", (), [(2,)]),
    ("compound", "INTERSECT ALL", f"SELECT X FROM {V3} INTERSECT ALL SELECT 2 {D}", (), [(2,)]),
    (
        "compound",
        "EXCEPT",
        f"SELECT X FROM {V3} EXCEPT SELECT 2 {D} ORDER BY 1",
        (),
        [(1,), (3,)],
    ),
    (
        "compound",
        "EXCEPT ALL",
        f"SELECT X FROM {V3} EXCEPT ALL SELECT 2 {D} ORDER BY 1",
        (),
        [(1,), (3,)],
    ),
    (
        "compound",
        "ORDER BY an expression of a result column",
        f"SELECT X FROM {VN} UNION SELECT 3 {D} ORDER BY X IS NOT NULL, X",
        (),
        None,
    ),
    (
        "compound",
        "wrapped: SELECT * FROM (<union>) ORDER BY expression",
        f"SELECT * FROM (SELECT X FROM {VN} UNION SELECT 3 {D}) ORDER BY X IS NOT NULL, X",
        (),
        [(None,), (1,), (2,), (3,)],
    ),
    (
        "compound",
        "wrapped with markers, ORDER BY + FETCH FIRST",
        f"SELECT * FROM (SELECT X FROM {VN} WHERE X > CAST(? AS INTEGER) UNION "
        f"SELECT CAST(? AS INTEGER) {D}) ORDER BY X DESC FETCH FIRST 2 ROWS ONLY",
        (0, 9),
        [(9,), (2,)],
    ),
    (
        "compound",
        "wrapped, correlated to the outer query",
        f"SELECT X, (SELECT * FROM ({CORRELATED_UNION}) ORDER BY Y FETCH FIRST 1 ROWS ONLY) "
        f"FROM {V3} ORDER BY X",
        (),
        None,
    ),
    (
        "compound",
        "wrapped with LATERAL, correlated to the outer query",
        f"SELECT X, (SELECT * FROM LATERAL ({CORRELATED_UNION}) ORDER BY Y "
        f"FETCH FIRST 1 ROWS ONLY) FROM {V3} ORDER BY X",
        (),
        [(1, 1), (2, 2), (3, 3)],
    ),
    (
        "compound",
        "wrapped with TABLE, correlated to the outer query",
        f"SELECT X, (SELECT * FROM TABLE ({CORRELATED_UNION}) ORDER BY Y "
        f"FETCH FIRST 1 ROWS ONLY) FROM {V3} ORDER BY X",
        (),
        [(1, 1), (2, 2), (3, 3)],
    ),
    (
        "compound",
        "wrapped with LATERAL, not correlated",
        f"SELECT * FROM LATERAL (SELECT X FROM {VN} UNION SELECT 3 {D}) ORDER BY X IS NOT NULL, X",
        (),
        [(None,), (1,), (2,), (3,)],
    ),
    (
        "compound",
        "not wrapped, correlated, ORDER BY column",
        f"SELECT X, ({CORRELATED_UNION} ORDER BY Y FETCH FIRST 1 ROWS ONLY) FROM {V3} ORDER BY X",
        (),
        [(1, 1), (2, 2), (3, 3)],
    ),
    (
        "compound",
        "typed markers in parts",
        f"SELECT CAST(? AS INTEGER) {D} UNION SELECT CAST(? AS INTEGER) {D} ORDER BY 1",
        (1, 2),
        [(1,), (2,)],
    ),
    (
        "compound",
        "parenthesised parts",
        f"(SELECT 1 {D}) UNION (SELECT 2 {D}) ORDER BY 1",
        (),
        [(1,), (2,)],
    ),
    (
        "compound",
        "ORDER BY + FETCH FIRST inside parenthesised part",
        f"(SELECT X FROM {V3} ORDER BY X FETCH FIRST 1 ROWS ONLY) UNION (SELECT 3 {D}) ORDER BY 1",
        (),
        [(1,), (3,)],
    ),
    (
        "compound",
        "OFFSET inside parenthesised part",
        f"(SELECT X FROM {V3} ORDER BY X OFFSET 1 ROWS FETCH FIRST 1 ROWS ONLY) "
        f"UNION (SELECT 9 {D}) ORDER BY 1",
        (),
        [(2,), (9,)],
    ),
    (
        "compound",
        "sliced parts as derived tables",
        f"SELECT * FROM (SELECT X FROM {V3} ORDER BY X FETCH FIRST 1 ROWS ONLY) A "
        f"UNION SELECT * FROM (SELECT 3 {D}) B ORDER BY 1",
        (),
        [(1,), (3,)],
    ),
    (
        "compound",
        "ORDER BY column name after UNION",
        f"SELECT X FROM {V3} UNION SELECT 9 AS X {D} ORDER BY X",
        (),
        [(1,), (2,), (3,), (9,)],
    ),
    (
        "compound",
        "FETCH FIRST after UNION",
        f"SELECT X FROM {V3} UNION SELECT 9 {D} ORDER BY 1 FETCH FIRST 2 ROWS ONLY",
        (),
        [(1,), (2,)],
    ),
    (
        "compound",
        "UNION in a subquery (IN)",
        f"SELECT 1 {D} WHERE 2 IN (SELECT 1 {D} UNION SELECT 2 {D})",
        (),
        [(1,)],
    ),
    # --- subqueries
    (
        "subquery",
        "IN (subquery with FETCH FIRST)",
        f"SELECT 1 {D} WHERE 1 IN (SELECT X FROM {V3} ORDER BY X FETCH FIRST 1 ROWS ONLY)",
        (),
        [(1,)],
    ),
    (
        "subquery",
        "IN (subquery with OFFSET)",
        f"SELECT 1 {D} WHERE 2 IN (SELECT X FROM {V3} ORDER BY X OFFSET 1 ROWS "
        "FETCH FIRST 1 ROWS ONLY)",
        (),
        [(1,)],
    ),
    (
        "subquery",
        "scalar subquery in GROUP BY",
        f"SELECT (SELECT 7 {D}), COUNT(*) FROM {V3} GROUP BY (SELECT 7 {D})",
        (),
        [(7, 3)],
    ),
    (
        "subquery",
        "GROUP BY 1 (select index)",
        f"SELECT X, COUNT(*) FROM {V3} GROUP BY 1 ORDER BY 1",
        (),
        [(1, 1), (2, 1), (3, 1)],
    ),
    (
        "subquery",
        "correlated scalar subquery in select list",
        f"SELECT X, (SELECT COUNT(*) FROM {V3.replace('T (X)', 'U (Y)')} WHERE Y < X) "
        f"FROM {V3} ORDER BY X",
        (),
        [(1, 0), (2, 1), (3, 2)],
    ),
    (
        "subquery",
        "EXISTS in select list",
        f"SELECT EXISTS (SELECT 1 {D}) {D}",
        (),
        [(True,)],
    ),
    (
        "subquery",
        "EXISTS in WHERE (control)",
        f"SELECT 1 {D} WHERE EXISTS (SELECT 1 {D})",
        (),
        [(1,)],
    ),
    (
        "subquery",
        "CASE WHEN EXISTS ... THEN 1 ELSE 0 in select list",
        f"SELECT CASE WHEN EXISTS (SELECT 1 {D}) THEN 1 ELSE 0 END {D}",
        (),
        [(1,)],
    ),
    (
        "subquery",
        "EXISTS in select list of a derived table's query",
        f"SELECT V FROM (SELECT CASE WHEN EXISTS (SELECT 1 {D}) THEN 1 ELSE 0 END V {D}) T",
        (),
        [(1,)],
    ),
    (
        "subquery",
        "CASE WHEN 1 IN (subquery) in select list",
        f"SELECT CASE WHEN 1 IN (SELECT 1 {D}) THEN 1 ELSE 0 END {D}",
        (),
        [(1,)],
    ),
    (
        "subquery",
        "CASE WHEN (SELECT COUNT(*) ...) > 0 in select list",
        f"SELECT CASE WHEN (SELECT COUNT(*) {D}) > 0 THEN 1 ELSE 0 END {D}",
        (),
        [(1,)],
    ),
    (
        "subquery",
        "CASE WHEN EXISTS in select list",
        f"SELECT CASE WHEN EXISTS (SELECT 1 {D}) THEN TRUE ELSE FALSE END {D}",
        (),
        [(True,)],
    ),
    # Exists() rewrite candidates for the select list (EXISTS is rejected
    # there): a scalar subquery that stops at the first row, IS NOT NULL.
    (
        "subquery",
        "(SELECT 1 ... FETCH FIRST 1 ROW ONLY) IS NOT NULL in select list",
        f"SELECT X, (SELECT 1 FROM {V3.replace('T (X)', 'U (Y)')} WHERE Y > X "
        f"FETCH FIRST 1 ROW ONLY) IS NOT NULL FROM {V3} ORDER BY X",
        (),
        [(1, True), (2, True), (3, False)],
    ),
    (
        "subquery",
        "CASE WHEN (SELECT 1 ... FETCH FIRST 1 ROW ONLY) IS NOT NULL THEN TRUE ELSE FALSE",
        f"SELECT X, CASE WHEN (SELECT 1 FROM {V3.replace('T (X)', 'U (Y)')} WHERE Y > X "
        f"FETCH FIRST 1 ROW ONLY) IS NOT NULL THEN TRUE ELSE FALSE END FROM {V3} ORDER BY X",
        (),
        [(1, True), (2, True), (3, False)],
    ),
    (
        "subquery",
        "first-row subquery IS NOT NULL with a marker",
        f"SELECT X, (SELECT 1 FROM {V3.replace('T (X)', 'U (Y)')} WHERE Y > X + "
        f"CAST(? AS INTEGER) FETCH FIRST 1 ROW ONLY) IS NOT NULL FROM {V3} ORDER BY X",
        (1,),
        [(1, True), (2, False), (3, False)],
    ),
    (
        "subquery",
        "first-row subquery IS NOT NULL in WHERE and ORDER BY",
        f"SELECT X FROM {V3} WHERE (SELECT 1 {D} WHERE X > 1 FETCH FIRST 1 ROW ONLY) "
        f"IS NOT NULL ORDER BY (SELECT 1 {D} WHERE X > 2 FETCH FIRST 1 ROW ONLY) IS NOT NULL, X",
        (),
        [(2,), (3,)],
    ),
    (
        "subquery",
        "COUNT(*) > 0 in select list (control)",
        f"SELECT X, (SELECT COUNT(*) FROM {V3.replace('T (X)', 'U (Y)')} WHERE Y > X) > 0 "
        f"FROM {V3} ORDER BY X",
        (),
        [(1, True), (2, True), (3, False)],
    ),
    (
        "subquery",
        "CASE WHEN EXISTS in WHERE",
        f"SELECT X FROM {V3} WHERE CASE WHEN EXISTS (SELECT 1 {D} WHERE X > 1) "
        "THEN TRUE ELSE FALSE END ORDER BY X",
        (),
        [(2,), (3,)],
    ),
    (
        "subquery",
        "EXISTS in ORDER BY",
        f"SELECT X FROM {V3} ORDER BY EXISTS (SELECT 1 {D} WHERE X > 1), X",
        (),
        None,
    ),
    (
        "subquery",
        "first-row subquery IS NOT NULL in GROUP BY",
        f"SELECT (SELECT 1 {D} WHERE X > 1 FETCH FIRST 1 ROW ONLY) IS NOT NULL, COUNT(*) "
        f"FROM {V3} GROUP BY (SELECT 1 {D} WHERE X > 1 FETCH FIRST 1 ROW ONLY) IS NOT NULL "
        "ORDER BY 2",
        (),
        [(False, 1), (True, 2)],
    ),
    (
        "subquery",
        "NOT (first-row subquery IS NOT NULL) in select list",
        f"SELECT X, NOT ((SELECT 1 {D} WHERE X > 1 FETCH FIRST 1 ROW ONLY) IS NOT NULL) "
        f"FROM {V3} ORDER BY X",
        (),
        [(1, True), (2, False), (3, False)],
    ),
    # A parameter marker in the select list of an EXISTS subquery (Django's
    # Exists selects Value(1)) fails in the host server.
    (
        "subquery",
        "EXISTS(SELECT CAST(? AS INTEGER) ...) in WHERE",
        f"SELECT 1 {D} WHERE EXISTS (SELECT CAST(? AS INTEGER) AS A {D})",
        (1,),
        None,
    ),
    (
        "subquery",
        "EXISTS(SELECT 1 ... WHERE marker) in WHERE",
        f"SELECT 1 {D} WHERE EXISTS (SELECT 1 FROM {V3} WHERE X = CAST(? AS INTEGER))",
        (2,),
        [(1,)],
    ),
    # --- boolean expressions
    ("boolean", "predicate in select list", f"SELECT 1 = 1 {D}", (), [(True,)]),
    (
        "boolean",
        "predicate on a column in select list",
        f"SELECT X > 1 FROM {V3} ORDER BY X",
        (),
        [(False,), (True,), (True,)],
    ),
    ("boolean", "BOOLEAN marker", f"SELECT CAST(? AS BOOLEAN) {D}", (True,), [(True,)]),
    (
        "boolean",
        "boolean column alone in WHERE",
        "SELECT 1 FROM (VALUES TRUE) T (B) WHERE B",
        (),
        [(1,)],
    ),
    (
        "boolean",
        "NOT boolean column",
        "SELECT 1 FROM (VALUES FALSE) T (B) WHERE NOT B",
        (),
        [(1,)],
    ),
    (
        "boolean",
        "predicate in GROUP BY",
        f"SELECT X < 2, COUNT(*) FROM {V3} GROUP BY X < 2 ORDER BY 2",
        (),
        [(True, 1), (False, 2)],
    ),
    (
        "boolean",
        "NOT predicate in select list",
        f"SELECT NOT (X < 2) FROM {V3} ORDER BY X",
        (),
        [(False,), (True,), (True,)],
    ),
    (
        "boolean",
        "CASE WHEN predicate THEN TRUE ELSE FALSE END in select list",
        f"SELECT CASE WHEN X < 2 THEN TRUE ELSE FALSE END FROM {V3} ORDER BY X",
        (),
        [(True,), (False,), (False,)],
    ),
    # A predicate with an untyped marker in the select list (Django: a Q /
    # lookup annotation with a plain value).
    ("boolean", "select list: X < ? (untyped marker)", f"SELECT X < ? FROM {V3}", (2,), None),
    (
        "boolean",
        "select list: CASE WHEN X < ? THEN TRUE ELSE FALSE END (untyped)",
        f"SELECT CASE WHEN X < ? THEN TRUE ELSE FALSE END FROM {V3}",
        (2,),
        None,
    ),
    (
        "boolean",
        "select list: X < CAST(? AS INTEGER)",
        f"SELECT X < CAST(? AS INTEGER) FROM {V3} ORDER BY X",
        (2,),
        [(True,), (False,), (False,)],
    ),
    (
        "boolean",
        "GROUP BY an expression with a marker (also selected)",
        f"SELECT CASE WHEN X < CAST(? AS INTEGER) THEN TRUE ELSE FALSE END, COUNT(*) FROM {V3} "
        "GROUP BY CASE WHEN X < CAST(? AS INTEGER) THEN TRUE ELSE FALSE END",
        (2, 2),
        None,
    ),
    (
        "boolean",
        "GROUP BY the same expression without a marker",
        f"SELECT CASE WHEN X < 2 THEN TRUE ELSE FALSE END, COUNT(*) FROM {V3} "
        "GROUP BY CASE WHEN X < 2 THEN TRUE ELSE FALSE END ORDER BY 2",
        (),
        [(True, 1), (False, 2)],
    ),
    # Predicates used as values (Django: lookups as expressions, filter(x=Q(...)))
    (
        "boolean",
        "WHERE (pred) = (pred)",
        f"SELECT X FROM {V3} WHERE (X < 3) = (X < 2) ORDER BY X",
        (),
        [(1,), (3,)],
    ),
    (
        "boolean",
        "WHERE pred = pred (no parentheses)",
        f"SELECT X FROM {V3} WHERE X < 3 = X < 2",
        (),
        None,
    ),
    (
        "boolean",
        "WHERE boolean column = (pred)",
        "SELECT X FROM (VALUES (1, TRUE), (5, TRUE)) T (X, B) WHERE B = (X < 3)",
        (),
        [(1,)],
    ),
    (
        "boolean",
        "WHERE (pred) = TRUE",
        f"SELECT X FROM {V3} WHERE (X < 2) = TRUE",
        (),
        [(1,)],
    ),
    (
        "boolean",
        "WHERE CASE WHEN pred THEN TRUE ELSE FALSE END = CASE ...",
        f"SELECT X FROM {V3} WHERE CASE WHEN X < 3 THEN TRUE ELSE FALSE END = "
        "CASE WHEN X < 2 THEN TRUE ELSE FALSE END ORDER BY X",
        (),
        [(1,), (3,)],
    ),
    (
        "boolean",
        "WHERE boolean column = CASE WHEN pred THEN TRUE ELSE FALSE END",
        "SELECT X FROM (VALUES (1, TRUE), (5, TRUE)) T (X, B) "
        "WHERE B = CASE WHEN X < 3 THEN TRUE ELSE FALSE END",
        (),
        [(1,)],
    ),
    (
        "boolean",
        "select list: (pred) in parentheses",
        f"SELECT (X < 2) FROM {V3} ORDER BY X",
        (),
        [(True,), (False,), (False,)],
    ),
    (
        "boolean",
        "select list: CASE WHEN pred THEN 1 ELSE 0 END = (pred)",
        f"SELECT X FROM {V3} WHERE CASE WHEN X < 3 THEN 1 ELSE 0 END = (X < 2)",
        (),
        None,
    ),
    # Untyped markers / NULL as operands
    ("boolean", "WHERE ? > ? (untyped markers)", f"SELECT 1 {D} WHERE ? > ?", (2, 1), None),
    (
        "boolean",
        "WHERE CAST(? AS INTEGER) > ?",
        f"SELECT 1 {D} WHERE CAST(? AS INTEGER) > ?",
        (2, 1),
        [(1,)],
    ),
    ("boolean", "WHERE NULL IS NULL (untyped NULL)", f"SELECT 1 {D} WHERE NULL IS NULL", (), None),
    # --- NULL ordering
    ("nulls", "ORDER BY ASC (NULL position)", f"SELECT X FROM {VN} ORDER BY X", (), None),
    ("nulls", "ORDER BY DESC (NULL position)", f"SELECT X FROM {VN} ORDER BY X DESC", (), None),
    (
        "nulls",
        "ASC NULLS FIRST",
        f"SELECT X FROM {VN} ORDER BY X ASC NULLS FIRST",
        (),
        [(None,), (1,), (2,)],
    ),
    (
        "nulls",
        "DESC NULLS LAST",
        f"SELECT X FROM {VN} ORDER BY X DESC NULLS LAST",
        (),
        [(2,), (1,), (None,)],
    ),
    # Django emulates NULLS FIRST / LAST with "<expr> IS [NOT] NULL, <expr>".
    (
        "nulls",
        "ORDER BY X IS NOT NULL, X (emulated NULLS FIRST)",
        f"SELECT X FROM {VN} ORDER BY X IS NOT NULL, X",
        (),
        [(None,), (1,), (2,)],
    ),
    (
        "nulls",
        "same with SELECT DISTINCT",
        f"SELECT DISTINCT X FROM {VN} ORDER BY X IS NOT NULL, X",
        (),
        [(None,), (1,), (2,)],
    ),
    (
        "nulls",
        "SELECT DISTINCT with the predicate also selected",
        f"SELECT DISTINCT X, X IS NOT NULL FROM {VN} ORDER BY X IS NOT NULL, X",
        (),
        [(None, False), (1, True), (2, True)],
    ),
    (
        "nulls",
        "SELECT DISTINCT, CASE in ORDER BY",
        f"SELECT DISTINCT X FROM {VN} ORDER BY CASE WHEN X IS NULL THEN 0 ELSE 1 END, X",
        (),
        [(None,), (1,), (2,)],
    ),
    (
        "nulls",
        "DISTINCT, ORDER BY expression with a marker (also selected)",
        f"SELECT DISTINCT X + CAST(? AS INTEGER), X + CAST(? AS INTEGER) IS NOT NULL FROM {VN} "
        "ORDER BY X + CAST(? AS INTEGER) IS NOT NULL, X + CAST(? AS INTEGER)",
        (0, 0, 0, 0),
        [(None, False), (1, True), (2, True)],
    ),
    (
        "nulls",
        "DISTINCT, ORDER BY select-list positions (with markers)",
        f"SELECT DISTINCT X + CAST(? AS INTEGER), X + CAST(? AS INTEGER) IS NOT NULL FROM {VN} "
        "ORDER BY 2 ASC, 1 ASC",
        (0, 0),
        [(None, False), (1, True), (2, True)],
    ),
    # --- regular expressions
    ("regex", "REGEXP_LIKE", f"SELECT 1 {D} WHERE REGEXP_LIKE('abc', 'a.c')", (), [(1,)]),
    (
        "regex",
        "REGEXP_LIKE with marker pattern",
        f"SELECT 1 {D} WHERE REGEXP_LIKE('abc', CAST(? AS NVARCHAR(100)))",
        ("^a",),
        [(1,)],
    ),
    (
        "regex",
        "REGEXP_LIKE flag i",
        f"SELECT 1 {D} WHERE REGEXP_LIKE('ABC', 'abc', 'i')",
        (),
        [(1,)],
    ),
    (
        "regex",
        "backreference",
        f"SELECT 1 {D} WHERE REGEXP_LIKE('abab', '^(ab)\\1$')",
        (),
        [(1,)],
    ),
    (
        "regex",
        "REGEXP_LIKE with an untyped marker pattern",
        f"SELECT 1 {D} WHERE REGEXP_LIKE('abc', ?)",
        ("^a",),
        [(1,)],
    ),
    (
        "regex",
        "REGEXP_LIKE on an INTEGER source",
        f"SELECT X FROM {V3} WHERE REGEXP_LIKE(X, ?)",
        ("^2$",),
        [(2,)],
    ),
    (
        "regex",
        "REGEXP_LIKE on NULL with '^$'",
        f"SELECT X FROM {VN} WHERE REGEXP_LIKE(X, '^$')",
        (),
        [],
    ),
    (
        "regex",
        "REGEXP_LIKE non-ASCII pattern as untyped marker (job CCSID)",
        f"SELECT 1 {D} WHERE REGEXP_LIKE(CAST(? AS NVARCHAR(20)), ?)",
        ("Grüße 😀", "^Grü.e 😀$"),
        None,
    ),
    (
        "regex",
        "REGEXP_LIKE non-ASCII pattern as typed marker",
        f"SELECT 1 {D} WHERE REGEXP_LIKE(CAST(? AS NVARCHAR(20)), CAST(? AS NVARCHAR(16370)))",
        ("Grüße 😀", "^Grü.e 😀$"),
        [(1,)],
    ),
    (
        "regex",
        "REGEXP_LIKE flag i with non-ASCII",
        f"SELECT 1 {D} WHERE REGEXP_LIKE(CAST(? AS NVARCHAR(20)), ?, 'i')",
        ("ÜBER", "^über$"),
        [(1,)],
    ),
    # --- arithmetic and bit functions
    ("arith", "integer division 7 / 2", f"SELECT 7 / 2 {D}", (), [(3,)]),
    ("arith", "-7 / 2 (truncation)", f"SELECT -7 / 2 {D}", (), [(-3,)]),
    (
        "arith",
        "typed markers / ",
        f"SELECT CAST(? AS INTEGER) / CAST(? AS INTEGER) {D}",
        (7, 2),
        [(3,)],
    ),
    ("arith", "MOD(7, 3)", f"SELECT MOD(7, 3) {D}", (), [(1,)]),
    ("arith", "MOD(-7, 3)", f"SELECT MOD(-7, 3) {D}", (), None),
    ("arith", "POWER(2, 10)", f"SELECT POWER(2, 10) {D}", (), None),
    ("arith", "POWER(2.5, 2)", f"SELECT POWER(2.5, 2) {D}", (), None),
    ("arith", "BITAND(12, 10)", f"SELECT BITAND(12, 10) {D}", (), [(8,)]),
    ("arith", "BITOR(12, 10)", f"SELECT BITOR(12, 10) {D}", (), [(14,)]),
    ("arith", "BITXOR(12, 10)", f"SELECT BITXOR(12, 10) {D}", (), [(6,)]),
    ("arith", "BITNOT(0)", f"SELECT BITNOT(0) {D}", (), [(-1,)]),
    ("arith", "shift left via * POWER(2, n)", f"SELECT 3 * POWER(2, 2) {D}", (), None),
    ("arith", "DECIMAL + DOUBLE type", f"SELECT 1.5 + 1.5E0 {D}", (), None),
    # --- strings
    (
        "string",
        "CONCAT with NULL",
        f"SELECT CONCAT('a', CAST(NULL AS VARCHAR(1))) {D}",
        (),
        [(None,)],
    ),
    ("string", "|| with NULL", f"SELECT 'a' || CAST(NULL AS VARCHAR(1)) {D}", (), [(None,)]),
    (
        "string",
        "LIKE marker ESCAPE '\\'",
        f"SELECT 1 {D} WHERE 'a%b' LIKE CAST(? AS NVARCHAR(10)) ESCAPE '\\'",
        ("a\\%b",),
        [(1,)],
    ),
    (
        "string",
        "LIKE column ESCAPE with % in data",
        f"SELECT 1 {D} WHERE 'a_b' LIKE 'a\\_%' ESCAPE '\\'",
        (),
        [(1,)],
    ),
    (
        "string",
        "UPPER on NVARCHAR marker",
        f"SELECT UPPER(CAST(? AS NVARCHAR(10))) {D}",
        ("straße",),
        None,
    ),
    # --- LOB (NCLOB) values
    ("lob", "ORDER BY NCLOB", f"SELECT K FROM {LOB} ORDER BY L, K", (), [(2,), (1,), (3,)]),
    ("lob", "GROUP BY NCLOB", f"SELECT L, COUNT(*) FROM {LOB} GROUP BY L", (), None),
    ("lob", "DISTINCT NCLOB", f"SELECT DISTINCT L FROM {LOB}", (), None),
    ("lob", "NCLOB = NCLOB", f"SELECT K FROM {LOB} WHERE L = L ORDER BY K", (), None),
    ("lob", "NCLOB = marker", f"SELECT K FROM {LOB} WHERE L = ? ORDER BY K", ("b",), None),
    (
        "lob",
        "NCLOB = typed marker",
        f"SELECT K FROM {LOB} WHERE L = CAST(? AS NCLOB(1K)) ORDER BY K",
        ("b",),
        [(1,), (3,)],
    ),
    (
        "lob",
        "NCLOB LIKE marker",
        f"SELECT K FROM {LOB} WHERE L LIKE ? ORDER BY K",
        ("b%",),
        [(1,), (3,)],
    ),
    ("lob", "UPPER(NCLOB)", f"SELECT UPPER(L) FROM {LOB} ORDER BY K", (), None),
    (
        "lob",
        "NCLOB IN (subquery)",
        f"SELECT K FROM {LOB} WHERE L IN (SELECT L FROM {LOB})",
        (),
        None,
    ),
    (
        "lob",
        "ORDER BY CAST(NCLOB AS NVARCHAR(16370))",
        f"SELECT K FROM {LOB} ORDER BY CAST(L AS NVARCHAR(16370)), K",
        (),
        [(2,), (1,), (3,)],
    ),
    (
        "lob",
        "GROUP BY CAST(NCLOB AS NVARCHAR(16370))",
        f"SELECT CAST(L AS NVARCHAR(16370)) C, COUNT(*) FROM {LOB} "
        "GROUP BY CAST(L AS NVARCHAR(16370)) ORDER BY 1",
        (),
        [("a", 1), ("b", 2)],
    ),
    (
        "lob",
        "DISTINCT CAST(NCLOB AS NVARCHAR(16370))",
        f"SELECT DISTINCT CAST(L AS NVARCHAR(16370)) FROM {LOB} ORDER BY 1",
        (),
        [("a",), ("b",)],
    ),
    (
        "lob",
        "NCLOB in UNION (implies DISTINCT)",
        f"SELECT L FROM {LOB} UNION SELECT L FROM {LOB}",
        (),
        None,
    ),
    (
        "lob",
        "NCLOB in UNION ALL",
        f"SELECT L FROM {LOB} UNION ALL SELECT L FROM {LOB}",
        (),
        None,
    ),
    # Stored LOB columns in the catalog (read-only; an empty table still shows
    # whether the statement compiles): SYSPACKAGESTMTSTAT.STATEMENT_TEXT is a DBCLOB,
    # SYSVARIABLEDEP.PARM_SIGNATURE a BLOB.
    (
        "lob",
        "stored DBCLOB: ORDER BY",
        f"SELECT COUNT(*) FROM (SELECT STATEMENT_TEXT FROM {PKG} "
        "ORDER BY STATEMENT_TEXT FETCH FIRST 5 ROWS ONLY) T",
        (),
        None,
    ),
    (
        "lob",
        "stored DBCLOB: GROUP BY",
        f"SELECT COUNT(*) FROM (SELECT STATEMENT_TEXT, COUNT(*) N FROM {PKG} "
        "GROUP BY STATEMENT_TEXT) T",
        (),
        None,
    ),
    (
        "lob",
        "stored DBCLOB: DISTINCT",
        f"SELECT COUNT(*) FROM (SELECT DISTINCT STATEMENT_TEXT FROM {PKG}) T",
        (),
        None,
    ),
    (
        "lob",
        "stored BLOB: ORDER BY / DISTINCT",
        "SELECT COUNT(*) FROM (SELECT DISTINCT PARM_SIGNATURE FROM QSYS2.SYSVARIABLEDEP "
        "ORDER BY PARM_SIGNATURE) T",
        (),
        None,
    ),
    # --- aggregates
    (
        "aggregate",
        "STDDEV / STDDEV_SAMP",
        f"SELECT STDDEV(X), STDDEV_SAMP(X) FROM {V3}",
        (),
        None,
    ),
    (
        "aggregate",
        "VARIANCE / VAR_SAMP",
        f"SELECT VARIANCE(X), VAR_SAMP(X) FROM {V3}",
        (),
        None,
    ),
    ("aggregate", "AVG of INTEGER (type)", f"SELECT AVG(X) FROM {V3}", (), None),
    ("aggregate", "COUNT(DISTINCT)", f"SELECT COUNT(DISTINCT X) FROM {V3}", (), [(3,)]),
    ("aggregate", "ANY_VALUE", f"SELECT ANY_VALUE(X) FROM {V3}", (), None),
    ("aggregate", "BIT_AND", f"SELECT BIT_AND(X) FROM {V3}", (), None),
    (
        "aggregate",
        "LISTAGG WITHIN GROUP",
        f"SELECT LISTAGG(CHAR(X), ',') WITHIN GROUP (ORDER BY X) FROM {V3}",
        (),
        None,
    ),
    (
        "aggregate",
        "FILTER (WHERE)",
        f"SELECT COUNT(*) FILTER (WHERE X > 1) FROM {V3}",
        (),
        [(2,)],
    ),
    (
        "aggregate",
        "aggregate over empty set",
        f"SELECT SUM(X), COUNT(X) FROM {V3} WHERE X > 9",
        (),
        [(None, 0)],
    ),
    (
        "aggregate",
        "COALESCE(aggregate, typed marker)",
        f"SELECT COALESCE(SUM(X), CAST(? AS INTEGER)) FROM {V3} WHERE X > 9",
        (0,),
        [(0,)],
    ),
    # --- GROUP BY an expression with a parameter marker: candidate fixes
    (
        "groupby",
        "baseline: marker in select and GROUP BY",
        f"SELECT MOD(X, CAST(? AS INTEGER)), COUNT(*) FROM {V3} GROUP BY MOD(X, CAST(? AS INTEGER))",
        (2, 2),
        None,
    ),
    (
        "groupby",
        "baseline: untyped marker in select and GROUP BY",
        f"SELECT MOD(X, ?), COUNT(*) FROM {V3} GROUP BY MOD(X, ?)",
        (2, 2),
        None,
    ),
    (
        "groupby",
        "baseline: COUNT(*) over a grouped subquery with markers",
        f"SELECT COUNT(*) FROM (SELECT MOD(X, CAST(? AS INTEGER)) AS M, COUNT(*) AS C "
        f"FROM {V3} GROUP BY MOD(X, CAST(? AS INTEGER))) S",
        (2, 2),
        None,
    ),
    (
        "groupby",
        "GROUP BY select alias",
        f"SELECT MOD(X, CAST(? AS INTEGER)) AS M, COUNT(*) FROM {V3} GROUP BY M",
        (2,),
        None,
    ),
    (
        "groupby",
        "inline: integer literal",
        f"SELECT MOD(X, 2), COUNT(*) FROM {V3} GROUP BY MOD(X, 2) ORDER BY 1",
        (),
        [(0, 1), (1, 2)],
    ),
    (
        "groupby",
        "inline: typed integer literal",
        f"SELECT MOD(X, CAST(2 AS INTEGER)), COUNT(*) FROM {V3} "
        f"GROUP BY MOD(X, CAST(2 AS INTEGER)) ORDER BY 1",
        (),
        [(0, 1), (1, 2)],
    ),
    (
        "groupby",
        "inline: literal in GROUP BY, marker in select",
        f"SELECT MOD(X, CAST(? AS INTEGER)), COUNT(*) FROM {V3} GROUP BY MOD(X, CAST(2 AS INTEGER))",
        (2,),
        None,
    ),
    (
        "groupby",
        "inline: boolean predicate with literals",
        f"SELECT CASE WHEN X < CAST(2 AS INTEGER) THEN TRUE ELSE FALSE END, COUNT(*) FROM {V3} "
        f"GROUP BY CASE WHEN X < CAST(2 AS INTEGER) THEN TRUE ELSE FALSE END ORDER BY 2",
        (),
        [(True, 1), (False, 2)],
    ),
    (
        "groupby",
        "inline: CASE with BOOLEAN and DOUBLE literals",
        f"SELECT CASE WHEN X > CAST(1.5E0 AS DOUBLE) THEN CAST(TRUE AS BOOLEAN) "
        f"ELSE CAST(FALSE AS BOOLEAN) END, COUNT(*) FROM {V3} "
        f"GROUP BY CASE WHEN X > CAST(1.5E0 AS DOUBLE) THEN CAST(TRUE AS BOOLEAN) "
        f"ELSE CAST(FALSE AS BOOLEAN) END ORDER BY 2",
        (),
        [(False, 1), (True, 2)],
    ),
    (
        "groupby",
        "inline: DECIMAL literal",
        f"SELECT X * CAST(1.5 AS DECIMAL(2, 1)), COUNT(*) FROM {V3} "
        f"GROUP BY X * CAST(1.5 AS DECIMAL(2, 1)) ORDER BY 1",
        (),
        None,
    ),
    (
        "groupby",
        "inline: nested aggregate over grouped expression",
        f"SELECT LEAST(MIN(X), GREATEST(X, CAST(2 AS INTEGER))) FROM {V3} "
        f"GROUP BY GREATEST(X, CAST(2 AS INTEGER)) ORDER BY 1",
        (),
        [(1,), (3,)],
    ),
    (
        "groupby",
        "grouped expression nested in a select expression (no literal)",
        f"SELECT X + X + 1, COUNT(*) FROM {V3} GROUP BY X + X ORDER BY 1",
        (),
        None,
    ),
    (
        "groupby",
        "grouped expression nested with an aggregate (no literal)",
        f"SELECT LEAST(MIN(X), X + X) FROM {V3} GROUP BY X + X ORDER BY 1",
        (),
        None,
    ),
    (
        "groupby",
        "grouped column nested with an aggregate",
        f"SELECT LEAST(MIN(X), X) FROM {V3} GROUP BY X ORDER BY 1",
        (),
        None,
    ),
    (
        "groupby",
        "inline: COUNT(*) over a grouped subquery",
        f"SELECT COUNT(*) FROM (SELECT MOD(X, CAST(2 AS INTEGER)) AS M, COUNT(*) AS C "
        f"FROM {V3} GROUP BY MOD(X, CAST(2 AS INTEGER))) S",
        (),
        [(2,)],
    ),
    (
        "groupby",
        "derived table: marker inside, GROUP BY the column",
        f"SELECT M, COUNT(*) FROM (SELECT X, MOD(X, CAST(? AS INTEGER)) AS M FROM {V3}) T "
        f"GROUP BY M ORDER BY M",
        (2,),
        [(0, 1), (1, 2)],
    ),
    (
        "groupby",
        "derived table: boolean predicate with markers",
        f"SELECT B, COUNT(*) FROM (SELECT X, CASE WHEN X < CAST(? AS INTEGER) THEN TRUE "
        f"ELSE FALSE END AS B FROM {V3}) T GROUP BY B ORDER BY 2",
        (2,),
        [(True, 1), (False, 2)],
    ),
    (
        "groupby",
        "derived table: nested aggregate",
        f"SELECT LEAST(MIN(X), G) FROM (SELECT X, GREATEST(X, CAST(? AS INTEGER)) AS G "
        f"FROM {V3}) T GROUP BY G ORDER BY 1",
        (2,),
        [(1,), (3,)],
    ),
    (
        "groupby",
        "derived table: marker in outer select and HAVING",
        f"SELECT M, COUNT(*) + CAST(? AS INTEGER) FROM (SELECT X, MOD(X, CAST(? AS INTEGER)) "
        f"AS M FROM {V3}) T GROUP BY M HAVING COUNT(*) > CAST(? AS INTEGER) ORDER BY M",
        (10, 2, 1),
        [(1, 12)],
    ),
    (
        "groupby",
        "derived table: COUNT(*) over it",
        f"SELECT COUNT(*) FROM (SELECT M, COUNT(*) AS C FROM (SELECT X, MOD(X, CAST(? AS "
        f"INTEGER)) AS M FROM {V3}) T GROUP BY M) S",
        (2,),
        [(2,)],
    ),
    # --- aggregates (aggregation module)
    ("aggregate", "COUNT(NULL)", f"SELECT COUNT(NULL) FROM {V3}", (), None),
    (
        "aggregate",
        "COUNT(CAST(NULL AS INTEGER))",
        f"SELECT COUNT(CAST(NULL AS INTEGER)) FROM {V3}",
        (),
        [(0,)],
    ),
    (
        "aggregate",
        "AVG(DOUBLE(X)) of INTEGER",
        f"SELECT AVG(CAST(X AS DOUBLE)) FROM (VALUES 1, 2) T (X)",
        (),
        [(1.5,)],
    ),
    (
        "aggregate",
        "LISTAGG with a typed marker delimiter",
        f"SELECT LISTAGG(CHAR(X), CAST(? AS VARCHAR(10))) FROM {V3}",
        (",",),
        None,
    ),
    (
        "aggregate",
        "LISTAGG without WITHIN GROUP, CASE argument",
        f"SELECT LISTAGG(CASE WHEN X > 1 THEN CHAR(X) END, ',') FROM {V3}",
        (),
        None,
    ),
    (
        "aggregate",
        "LISTAGG of NVARCHAR (type)",
        f"SELECT LISTAGG(CAST(CHAR(X) AS NVARCHAR(10)), ',') FROM {V3}",
        (),
        None,
    ),
    (
        "temporal",
        "DATE_TRUNC('MONTH', TIMESTAMP)",
        f"SELECT DATE_TRUNC('MONTH', TIMESTAMP('2026-10-18-12.34.56')) {D}",
        (),
        None,
    ),
    (
        "temporal",
        "TRUNC_TIMESTAMP(TIMESTAMP, 'MONTH')",
        f"SELECT TRUNC_TIMESTAMP(TIMESTAMP('2026-10-18-12.34.56'), 'MONTH') {D}",
        (),
        None,
    ),
    (
        "temporal",
        "TRUNC(DATE, 'MONTH')",
        f"SELECT TRUNC(DATE('2026-10-18'), 'MONTH') {D}",
        (),
        None,
    ),
    # --- temporal
    (
        "temporal",
        "TIMESTAMP - TIMESTAMP",
        f"SELECT TIMESTAMP('2026-10-18-12.00.00.000001') - TIMESTAMP('2026-10-17-10.30.00') {D}",
        (),
        None,
    ),
    (
        "temporal",
        "TIMESTAMPDIFF(1, ...) microseconds",
        f"SELECT TIMESTAMPDIFF(1, CHAR(TIMESTAMP('2026-10-18-12.00.00.000001') - "
        f"TIMESTAMP('2026-10-17-10.30.00'))) {D}",
        (),
        None,
    ),
    (
        "temporal",
        "DATE compared with a string",
        f"SELECT 1 {D} WHERE DATE('2026-10-18') > '2000-01-01'",
        (),
        [(1,)],
    ),
    (
        "temporal",
        "TIMESTAMP + microseconds",
        f"SELECT TIMESTAMP('2026-10-18-00.00.00') + 1500000 MICROSECONDS {D}",
        (),
        None,
    ),
]


def attempt(conn, sql: str, params: tuple) -> tuple[bool, Any]:
    import pyodbc

    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        rows = [tuple(row) for row in cursor.fetchall()]
        return True, rows
    except pyodbc.Error as exc:
        message = str(exc.args[1] if len(exc.args) > 1 else exc)
        code = _SQLCODE.search(message)
        text = re.sub(r"^(\[[^\]]*\]\s*)+", "", message)
        return False, f"{code.group(1) if code else exc.args[0]}: {text[:110]}"
    finally:
        cursor.close()


def max_params(conn) -> dict[str, Any]:
    """The largest number of parameter markers accepted in one statement."""
    found: dict[str, Any] = {}
    for n in (1000, 2000, 4096, 8192, 10000, 32767, 32768, 65535):
        markers = ", ".join(["CAST(? AS INTEGER)"] * n)
        ok, detail = attempt(conn, f"SELECT 1 {D} WHERE 1 IN ({markers})", tuple(range(n)))
        found[str(n)] = "ok" if ok else detail
        if not ok:
            break
    return found


def run(settings: Settings, conn) -> dict[str, Any]:
    results: dict[str, Any] = {}
    area = None
    for check_area, label, sql, params, want in CHECKS:
        if check_area != area:
            area = check_area
            print(f"\n# {area}")
        ok, detail = attempt(conn, sql, params)
        if ok:
            shown = [tuple(_plain(v) for v in row) for row in detail]
            verdict = "ok" if want is None or shown == want else f"UNEXPECTED (want {want})"
            line = f"{verdict}: {shown}"
        else:
            line = f"error {detail}"
        results[f"{area}: {label}"] = line
        print(f"  {label:<48} {line}")
    print("\n# parameter markers")
    results["max_params"] = max_params(conn)
    for n, outcome in results["max_params"].items():
        print(f"  {n:>6} markers: {outcome}")
    return results


def _plain(value: Any) -> Any:
    from decimal import Decimal

    if isinstance(value, Decimal):
        return str(value)
    return value
