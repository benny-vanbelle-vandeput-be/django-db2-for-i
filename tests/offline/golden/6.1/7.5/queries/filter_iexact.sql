-- golden: queries/filter_iexact
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["Ada"]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE UPPER("TESTAPP_AUTHOR"."NAME") = UPPER(%s);
