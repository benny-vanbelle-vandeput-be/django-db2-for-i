-- golden: queries/filter_startswith_escaped
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["50\\%\\_off%"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" LIKE %s ESCAPE '\';
