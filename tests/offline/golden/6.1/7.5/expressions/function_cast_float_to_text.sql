-- golden: expressions/function_cast_float_to_text
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: unverified
SELECT CAST(CAST(CAST("TESTAPP_MEASURE"."AMOUNT" AS DOUBLE) AS DECFLOAT(16)) + 0 AS NVARCHAR(16370)) AS "X" FROM "TESTAPP_MEASURE";
