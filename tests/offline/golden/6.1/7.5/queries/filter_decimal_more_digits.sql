-- golden: queries/filter_decimal_more_digits
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_measure
-- params: [[{"$decimal": "1.005"}]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-20
SELECT "TESTAPP_MEASURE"."ID", "TESTAPP_MEASURE"."SMALL", "TESTAPP_MEASURE"."AMOUNT", "TESTAPP_MEASURE"."BIG" FROM "TESTAPP_MEASURE" WHERE "TESTAPP_MEASURE"."AMOUNT" = CAST(%s AS DECIMAL(4, 3));
