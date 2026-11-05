-- golden: expressions/function_concat
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["", "!", ""]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-11-03
SELECT CONCAT(COALESCE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(32))), CONCAT(CAST(%s AS NVARCHAR(32)), COALESCE("TESTAPP_AUTHOR"."NAME", CAST(%s AS NVARCHAR(32))))) AS "X" FROM "TESTAPP_AUTHOR";
