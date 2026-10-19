-- golden: expressions/operator_left_shift
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[2]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT (("TESTAPP_AUTHOR"."ID" * BIGINT(POWER(2, CAST(%s AS INTEGER))))) AS "X" FROM "TESTAPP_AUTHOR";
