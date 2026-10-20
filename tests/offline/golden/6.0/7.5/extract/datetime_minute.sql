-- golden: extract/datetime_minute
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT MINUTE("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
