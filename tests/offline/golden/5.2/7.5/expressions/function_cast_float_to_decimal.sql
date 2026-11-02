-- golden: expressions/function_cast_float_to_decimal
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: unverified
SELECT CAST(ROUND(CAST(CAST("TESTAPP_MEASURE"."AMOUNT" AS DOUBLE) AS DECFLOAT(34)), 1) AS DECIMAL(8, 1)) AS "X" FROM "TESTAPP_MEASURE";
