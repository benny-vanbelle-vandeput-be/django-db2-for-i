-- golden: expressions/function_length
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-03
SELECT CHARACTER_LENGTH("TESTAPP_AUTHOR"."NAME") AS "X" FROM "TESTAPP_AUTHOR";
