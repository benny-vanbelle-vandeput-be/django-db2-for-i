-- golden: queries/slice_first_only
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" ORDER BY "TESTAPP_AUTHOR"."ID" ASC FETCH FIRST 2 ROWS ONLY;
