-- golden: queries/slice_offset_only
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" ORDER BY "TESTAPP_AUTHOR"."ID" ASC OFFSET 3 ROWS;
