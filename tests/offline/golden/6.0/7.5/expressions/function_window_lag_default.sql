-- golden: expressions/function_window_lag_default
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[0]]
-- verified: unverified
SELECT LAG("TESTAPP_MEASURE"."AMOUNT", 2, CAST(%s AS INTEGER)) OVER (ORDER BY "TESTAPP_MEASURE"."BIG" ASC) AS "X" FROM "TESTAPP_MEASURE";
