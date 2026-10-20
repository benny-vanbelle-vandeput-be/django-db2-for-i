-- golden: queries/difference_ordered
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["a%", "%z"]]
-- verified: unverified
SELECT * FROM LATERAL ( (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\') EXCEPT (SELECT "TESTAPP_AUTHOR"."ID" AS "COL1", "TESTAPP_AUTHOR"."NAME" AS "COL2" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\') ) ORDER BY "COL2" DESC;
