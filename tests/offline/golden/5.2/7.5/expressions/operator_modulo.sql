-- golden: expressions/operator_modulo
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[3]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT (MOD("TESTAPP_AUTHOR"."ID", CAST(%s AS INTEGER))) AS "X" FROM "TESTAPP_AUTHOR";
