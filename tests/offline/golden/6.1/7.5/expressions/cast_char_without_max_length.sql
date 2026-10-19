-- golden: expressions/cast_char_without_max_length
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT CAST("TESTAPP_AUTHOR"."ID" AS NVARCHAR(16370)) AS "X" FROM "TESTAPP_AUTHOR";
