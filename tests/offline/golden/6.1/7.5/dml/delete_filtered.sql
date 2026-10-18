-- golden: dml/delete_filtered
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["tmp%"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
DELETE FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\';
