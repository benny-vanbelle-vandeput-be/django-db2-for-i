-- golden: expressions/function_window_cume_dist
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.10, 2026-11-05
SELECT CAST(CUME_DIST() OVER (ORDER BY "TESTAPP_MEASURE"."AMOUNT" DESC) AS DOUBLE) AS "X" FROM "TESTAPP_MEASURE";
