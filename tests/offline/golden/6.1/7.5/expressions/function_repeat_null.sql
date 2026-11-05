-- golden: expressions/function_repeat_null
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-11-03
SELECT REPEAT("TESTAPP_AUTHOR"."NAME", CAST(NULL AS INTEGER)) AS "X" FROM "TESTAPP_AUTHOR";
