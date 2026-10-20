-- golden: queries/filter_iexact_wildcards
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["50%_Off\\x"]]
-- verified: unverified
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE UPPER("TESTAPP_AUTHOR"."NAME") = UPPER(%s);
