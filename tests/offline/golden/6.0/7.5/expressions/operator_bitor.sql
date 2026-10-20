-- golden: expressions/operator_bitor
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[6]]
-- verified: unverified
SELECT (BITOR("TESTAPP_AUTHOR"."ID", CAST(%s AS INTEGER))) AS "X" FROM "TESTAPP_AUTHOR";
