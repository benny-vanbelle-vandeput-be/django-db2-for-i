-- golden: expressions/function_atan2
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[]]
-- verified: unverified
SELECT ATAN2("TESTAPP_MEASURE"."BIG", "TESTAPP_MEASURE"."SMALL") AS "X" FROM "TESTAPP_MEASURE";
