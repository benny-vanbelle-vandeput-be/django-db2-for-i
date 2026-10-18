-- golden: queries/exists
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1, "a"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT CAST(%s AS INTEGER) AS "A" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s FETCH FIRST 1 ROWS ONLY;
