-- golden: dml/delete_filtered
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["tmp%"]]
-- verified: unverified
DELETE FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\';
