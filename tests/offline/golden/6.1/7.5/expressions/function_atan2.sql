-- golden: expressions/function_atan2
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-11-03
SELECT ATAN2("TESTAPP_MEASURE"."BIG", "TESTAPP_MEASURE"."SMALL") AS "X" FROM "TESTAPP_MEASURE";
