-- golden: queries/filter_in_union_of_sliced_parts
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."ID" IN ((SELECT "U0"."ID" AS "PK" FROM "TESTAPP_AUTHOR" "U0" ORDER BY "U0"."NAME" ASC FETCH FIRST 1 ROWS ONLY) UNION (SELECT "U0"."ID" AS "PK" FROM "TESTAPP_AUTHOR" "U0" ORDER BY "U0"."NAME" DESC FETCH FIRST 1 ROWS ONLY));
