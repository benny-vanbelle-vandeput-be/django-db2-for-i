-- golden: queries/distinct_nulls_first_annotation
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT DISTINCT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME", (SELECT MAX("U0"."PUBLISHED") AS "M" FROM "TESTAPP_BOOK" "U0" WHERE "U0"."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID") GROUP BY "U0"."AUTHOR_ID") AS "LAST", (SELECT MAX("U0"."PUBLISHED") AS "M" FROM "TESTAPP_BOOK" "U0" WHERE "U0"."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID") GROUP BY "U0"."AUTHOR_ID") IS NOT NULL FROM "TESTAPP_AUTHOR" ORDER BY 4 ASC, 3 ASC;
