-- golden: extract/trunc_date_and_time_of_datetime
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT DATE("TESTAPP_BOOK"."PUBLISHED") AS "X", TIME("TESTAPP_BOOK"."PUBLISHED") AS "B" FROM "TESTAPP_BOOK";
