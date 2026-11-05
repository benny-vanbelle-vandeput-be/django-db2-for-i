-- golden: expressions/function_lpad_null
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[3, "x"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-03
SELECT LPAD(CAST(NULL AS NVARCHAR(32)), CAST(%s AS INTEGER), CAST(%s AS NVARCHAR(32))) AS "X" FROM "TESTAPP_AUTHOR";
