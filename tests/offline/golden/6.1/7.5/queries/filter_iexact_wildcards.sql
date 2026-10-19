-- golden: queries/filter_iexact_wildcards
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["50%_Off\\x"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE UPPER("TESTAPP_AUTHOR"."NAME") = UPPER(%s);
