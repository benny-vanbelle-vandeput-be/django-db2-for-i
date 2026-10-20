-- golden: aggregates/group_by_predicate_with_a_value
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[100, 100]]
-- verified: unverified
SELECT "DJDB2I_GROUPING"."G1" AS "B", COUNT("TESTAPP_BOOK"."ID") AS "N" FROM "TESTAPP_BOOK" CROSS JOIN LATERAL (SELECT CASE WHEN "TESTAPP_BOOK"."PAGES" < %s THEN TRUE WHEN NOT ("TESTAPP_BOOK"."PAGES" < %s) THEN FALSE END AS "G1" FROM SYSIBM.SYSDUMMY1) AS "DJDB2I_GROUPING" GROUP BY "DJDB2I_GROUPING"."G1";
