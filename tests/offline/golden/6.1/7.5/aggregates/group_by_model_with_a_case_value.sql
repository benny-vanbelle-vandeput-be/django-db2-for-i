-- golden: aggregates/group_by_model_with_a_case_value
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[100, true, false]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME", SUM("TESTAPP_BOOK"."PAGES") AS "N", "DJDB2I_GROUPING"."G1" AS "B" FROM "TESTAPP_AUTHOR" LEFT OUTER JOIN "TESTAPP_BOOK" ON ("TESTAPP_AUTHOR"."ID" = "TESTAPP_BOOK"."AUTHOR_ID") CROSS JOIN LATERAL (SELECT CASE WHEN "TESTAPP_BOOK"."PAGES" > %s THEN CAST(%s AS BOOLEAN) ELSE CAST(%s AS BOOLEAN) END AS "G1" FROM SYSIBM.SYSDUMMY1) AS "DJDB2I_GROUPING" GROUP BY "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME", "DJDB2I_GROUPING"."G1";
