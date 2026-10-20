-- golden: dml/delete_filtered
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["tmp%"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
DELETE FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\';
