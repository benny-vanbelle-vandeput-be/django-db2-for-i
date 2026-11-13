-- golden: values/none_operand
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-13
SELECT ("TESTAPP_AUTHOR"."ID" + CAST(NULL AS INTEGER)) AS "X" FROM "TESTAPP_AUTHOR";
