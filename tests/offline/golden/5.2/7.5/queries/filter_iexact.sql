-- golden: queries/filter_iexact
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["Ada"]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE UPPER("TESTAPP_AUTHOR"."NAME") = UPPER(%s);
