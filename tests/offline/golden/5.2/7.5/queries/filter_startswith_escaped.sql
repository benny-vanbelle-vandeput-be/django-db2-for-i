-- golden: queries/filter_startswith_escaped
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["50\\%\\_off%"]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\';
