-- golden: queries/union
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a", "b"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s UNION SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s;
