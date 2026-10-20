-- golden: queries/filter_exact_longer_than_column
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" WHERE "TESTAPP_AUTHOR"."NAME" = CAST(%s AS NVARCHAR(256));
