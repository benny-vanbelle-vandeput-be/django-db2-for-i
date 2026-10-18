-- golden: queries/order_by_exists
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" ORDER BY ((SELECT (1) AS "A" FROM "TESTAPP_BOOK" "U0" WHERE "U0"."AUTHOR_ID" = ("TESTAPP_AUTHOR"."ID") FETCH FIRST 1 ROWS ONLY) IS NOT NULL) DESC, "TESTAPP_AUTHOR"."ID" ASC;
