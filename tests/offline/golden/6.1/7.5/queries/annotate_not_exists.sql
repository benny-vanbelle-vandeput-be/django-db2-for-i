-- golden: queries/annotate_not_exists
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT NOT ((SELECT (1) AS "A" FROM "TESTAPP_BOOK" "U0" WHERE "U0"."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID") FETCH FIRST 1 ROWS ONLY) IS NOT NULL) AS "HAS" FROM "TESTAPP_AUTHOR";
