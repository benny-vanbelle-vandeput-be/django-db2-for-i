-- golden: expressions/function_window_cume_dist
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.3, 2026-11-04
SELECT CAST(CUME_DIST() OVER (ORDER BY "TESTAPP_MEASURE"."AMOUNT" DESC) AS DOUBLE) AS "X" FROM "TESTAPP_MEASURE";
