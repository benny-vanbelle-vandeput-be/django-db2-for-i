-- golden: expressions/function_window_lag_default
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[0]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-05
SELECT LAG("TESTAPP_MEASURE"."AMOUNT", 2, CAST(%s AS INTEGER)) OVER (ORDER BY "TESTAPP_MEASURE"."BIG" ASC) AS "X" FROM "TESTAPP_MEASURE";
