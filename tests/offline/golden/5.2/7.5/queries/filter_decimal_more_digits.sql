-- golden: queries/filter_decimal_more_digits
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[{"$decimal": "1.005"}]]
-- verified: unverified
SELECT "TESTAPP_MEASURE"."ID", "TESTAPP_MEASURE"."SMALL", "TESTAPP_MEASURE"."AMOUNT", "TESTAPP_MEASURE"."BIG" FROM "TESTAPP_MEASURE" WHERE "TESTAPP_MEASURE"."AMOUNT" = CAST(%s AS DECIMAL(4, 3));
