-- golden: queries/difference_ordered
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a%", "%z"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT * FROM LATERAL ( (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\') EXCEPT (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\') ) ORDER BY "COL2" DESC;
