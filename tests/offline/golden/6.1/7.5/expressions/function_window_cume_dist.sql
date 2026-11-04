-- golden: expressions/function_window_cume_dist
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: unverified
SELECT CAST(CUME_DIST() OVER (ORDER BY "TESTAPP_MEASURE"."AMOUNT" DESC) AS DOUBLE) AS "X" FROM "TESTAPP_MEASURE";
