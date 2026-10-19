-- golden: dml/delete_filtered
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["tmp%"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
DELETE FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\';
