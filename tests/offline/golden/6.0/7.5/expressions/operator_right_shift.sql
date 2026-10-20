-- golden: expressions/operator_right_shift
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [[1]]
-- verified: unverified
SELECT (BIGINT(FLOOR(CAST("TESTAPP_AUTHOR"."ID" AS DECFLOAT(34)) / CAST(POWER(2, CAST(%s AS INTEGER)) AS DECFLOAT(34))))) AS "X" FROM "TESTAPP_AUTHOR";
