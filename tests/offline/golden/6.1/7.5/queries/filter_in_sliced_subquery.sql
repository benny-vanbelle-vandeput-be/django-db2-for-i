-- golden: queries/filter_in_sliced_subquery
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."ID" IN (SELECT "U0"."AUTHOR_ID" AS "AUTHOR" FROM "TESTAPP_BOOK" "U0" ORDER BY "U0"."PUBLISHED" DESC OFFSET 1 ROWS FETCH FIRST 2 ROWS ONLY);
