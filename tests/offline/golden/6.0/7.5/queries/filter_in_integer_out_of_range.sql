-- golden: queries/filter_in_integer_out_of_range
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[1, 100000]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT "TESTAPP_MEASURE"."ID", "TESTAPP_MEASURE"."SMALL", "TESTAPP_MEASURE"."AMOUNT", "TESTAPP_MEASURE"."BIG" FROM "TESTAPP_MEASURE" WHERE "TESTAPP_MEASURE"."SMALL" IN (%s, CAST(%s AS DECIMAL(6, 0)));
