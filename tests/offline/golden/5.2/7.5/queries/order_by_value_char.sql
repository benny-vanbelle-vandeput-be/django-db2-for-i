-- golden: queries/order_by_value_char
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["1"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT "TESTAPP_AUTHOR"."ID", "TESTAPP_AUTHOR"."NAME" FROM "TESTAPP_AUTHOR" ORDER BY CAST(CAST(%s AS NVARCHAR(32)) AS NVARCHAR(16370)) ASC, "TESTAPP_AUTHOR"."NAME" DESC;
