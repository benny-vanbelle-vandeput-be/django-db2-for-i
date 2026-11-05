-- golden: expressions/function_cast_float_to_decimal
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-11-03
SELECT CAST(ROUND(CAST(CAST("TESTAPP_MEASURE"."AMOUNT" AS DOUBLE) AS DECFLOAT(34)), 1) AS DECIMAL(8, 1)) AS "X" FROM "TESTAPP_MEASURE";
