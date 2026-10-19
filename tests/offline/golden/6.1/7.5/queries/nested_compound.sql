-- golden: queries/nested_compound
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a", "b", "a%"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
((SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s) UNION (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = %s)) INTERSECT (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\');
