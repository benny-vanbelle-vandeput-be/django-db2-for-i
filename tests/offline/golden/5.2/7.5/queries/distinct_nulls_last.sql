-- golden: queries/distinct_nulls_last
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT DISTINCT "TESTAPP_BOOK"."TITLE" AS "TITLE", "TESTAPP_BOOK"."PUBLISHED" IS NULL, "TESTAPP_BOOK"."PUBLISHED" FROM "TESTAPP_BOOK" ORDER BY 2 ASC, 3 DESC;
