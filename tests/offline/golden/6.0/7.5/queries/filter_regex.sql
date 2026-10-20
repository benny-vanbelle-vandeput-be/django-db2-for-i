-- golden: queries/filter_regex
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["^A(d)a\\1?$"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE REGEXP_LIKE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(16370)));
