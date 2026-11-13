-- golden: values/none_operand
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-13
SELECT ("TESTAPP_AUTHOR"."ID" + CAST(NULL AS INTEGER)) AS "X" FROM "TESTAPP_AUTHOR";
