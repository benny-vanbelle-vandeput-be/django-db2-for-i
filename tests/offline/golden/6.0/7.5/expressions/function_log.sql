-- golden: expressions/function_log
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: unverified
SELECT (LN("TESTAPP_MEASURE"."BIG") / LN("TESTAPP_MEASURE"."SMALL")) AS "X" FROM "TESTAPP_MEASURE";
