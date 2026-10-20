-- golden: queries/union
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a", "b"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
(SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s) UNION (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s);
