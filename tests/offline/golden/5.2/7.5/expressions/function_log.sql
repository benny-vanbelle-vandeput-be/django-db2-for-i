-- golden: expressions/function_log
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.19, 2026-11-03
SELECT (LN("TESTAPP_MEASURE"."BIG") / LN("TESTAPP_MEASURE"."SMALL")) AS "X" FROM "TESTAPP_MEASURE";
