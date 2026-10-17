-- golden: queries/exists
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1, "a"]]
-- verified: unverified
SELECT %s AS "A" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s FETCH FIRST 1 ROWS ONLY;
