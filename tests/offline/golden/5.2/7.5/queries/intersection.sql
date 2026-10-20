-- golden: queries/intersection
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a%", "%z"]]
-- verified: unverified
(SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\') INTERSECT (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\');
