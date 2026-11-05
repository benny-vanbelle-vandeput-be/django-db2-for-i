-- golden: expressions/function_cast_float_to_text
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-04
SELECT CAST(CAST(CAST("TESTAPP_MEASURE"."AMOUNT" AS DOUBLE) AS DECFLOAT(16)) + 0 AS NVARCHAR(16370)) AS "X" FROM "TESTAPP_MEASURE";
