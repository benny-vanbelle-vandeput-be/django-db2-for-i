-- golden: expressions/operator_bitor
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[6]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT (BITOR("TESTAPP_AUTHOR"."ID", CAST(%s AS INTEGER))) AS "X" FROM "TESTAPP_AUTHOR";
