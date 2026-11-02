-- golden: expressions/function_cast_decimal_to_decimal
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: unverified
SELECT CAST(ROUND("TESTAPP_MEASURE"."AMOUNT", 1) AS DECIMAL(8, 1)) AS "X" FROM "TESTAPP_MEASURE";
