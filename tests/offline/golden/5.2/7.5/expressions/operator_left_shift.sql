-- golden: expressions/operator_left_shift
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[2]]
-- verified: unverified
SELECT (("TESTAPP_AUTHOR"."ID" * BIGINT(POWER(2, CAST(%s AS INTEGER))))) AS "X" FROM "TESTAPP_AUTHOR";
