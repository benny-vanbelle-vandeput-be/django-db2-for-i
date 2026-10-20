-- golden: queries/filter_in_sliced_subquery
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."ID" IN (SELECT U0."AUTHOR_ID" AS "AUTHOR" FROM "TESTAPP_BOOK" U0 ORDER BY U0."PUBLISHED" DESC OFFSET 1 ROWS FETCH FIRST 2 ROWS ONLY);
