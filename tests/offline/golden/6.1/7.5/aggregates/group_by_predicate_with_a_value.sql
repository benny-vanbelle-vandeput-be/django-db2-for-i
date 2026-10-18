-- golden: aggregates/group_by_predicate_with_a_value
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[100]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT "DJDB2I_GROUPING"."G1" AS "B", COUNT("TESTAPP_BOOK"."ID") AS "N" FROM "TESTAPP_BOOK" CROSS JOIN LATERAL (SELECT CASE WHEN "TESTAPP_BOOK"."PAGES" < %s THEN TRUE ELSE FALSE END AS "G1" FROM SYSIBM.SYSDUMMY1) AS "DJDB2I_GROUPING" GROUP BY "DJDB2I_GROUPING"."G1";
