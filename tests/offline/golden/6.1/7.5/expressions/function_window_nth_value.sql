-- golden: expressions/function_window_nth_value
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: unverified
SELECT NTH_VALUE("TESTAPP_MEASURE"."AMOUNT", 2) OVER (PARTITION BY "TESTAPP_MEASURE"."SMALL" ORDER BY "TESTAPP_MEASURE"."BIG") AS "X" FROM "TESTAPP_MEASURE";
