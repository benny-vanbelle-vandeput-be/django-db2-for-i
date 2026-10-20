-- golden: queries/distinct_nulls_last
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT DISTINCT "TESTAPP_BOOK"."TITLE" AS "TITLE", "TESTAPP_BOOK"."PUBLISHED" IS NULL, "TESTAPP_BOOK"."PUBLISHED" FROM "TESTAPP_BOOK" ORDER BY 2 ASC, 3 DESC;
