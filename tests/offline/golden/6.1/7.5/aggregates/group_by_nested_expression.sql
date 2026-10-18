-- golden: aggregates/group_by_nested_expression
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[600]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT LEAST(MIN("TESTAPP_BOOK"."PAGES"), "DJDB2I_GROUPING"."G1") AS "X" FROM "TESTAPP_BOOK" CROSS JOIN LATERAL (SELECT GREATEST("TESTAPP_BOOK"."PAGES", CAST(%s AS INTEGER)) AS "G1" FROM SYSIBM.SYSDUMMY1) AS "DJDB2I_GROUPING" GROUP BY "DJDB2I_GROUPING"."G1";
