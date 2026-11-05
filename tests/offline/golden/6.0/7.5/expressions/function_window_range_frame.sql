-- golden: expressions/function_window_range_frame
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.10, 2026-11-05
SELECT SUM("TESTAPP_MEASURE"."AMOUNT") OVER (ORDER BY "TESTAPP_MEASURE"."BIG" ASC RANGE BETWEEN 5 PRECEDING AND 5 FOLLOWING) AS "X" FROM "TESTAPP_MEASURE";
