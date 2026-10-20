-- golden: queries/filter_in_integer_out_of_range
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[1, 100000]]
-- verified: unverified
SELECT "TESTAPP_MEASURE"."ID", "TESTAPP_MEASURE"."SMALL", "TESTAPP_MEASURE"."AMOUNT", "TESTAPP_MEASURE"."BIG" FROM "TESTAPP_MEASURE" WHERE "TESTAPP_MEASURE"."SMALL" IN (%s, CAST(%s AS DECIMAL(6, 0)));
