-- golden: expressions/operator_power
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[2]]
-- verified: unverified
SELECT (POWER("TESTAPP_AUTHOR"."ID", CAST(%s AS INTEGER))) AS "X" FROM "TESTAPP_AUTHOR";
