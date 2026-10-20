-- golden: queries/filter_exists
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE EXISTS(SELECT (1) AS "A" FROM "TESTAPP_BOOK" U0 WHERE U0."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID") FETCH FIRST 1 ROWS ONLY);
