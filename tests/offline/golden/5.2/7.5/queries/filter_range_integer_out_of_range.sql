-- golden: queries/filter_range_integer_out_of_range
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[0, 100000]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT "TESTAPP_MEASURE"."ID", "TESTAPP_MEASURE"."SMALL", "TESTAPP_MEASURE"."AMOUNT", "TESTAPP_MEASURE"."BIG" FROM "TESTAPP_MEASURE" WHERE "TESTAPP_MEASURE"."SMALL" BETWEEN %s AND CAST(%s AS DECIMAL(6, 0));
