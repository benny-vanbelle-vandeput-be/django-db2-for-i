-- golden: queries/annotate_exists
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT ((SELECT (1) AS "A" FROM "TESTAPP_BOOK" U0 WHERE U0."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID") FETCH FIRST 1 ROWS ONLY) IS NOT NULL) AS "HAS" FROM "TESTAPP_AUTHOR";
