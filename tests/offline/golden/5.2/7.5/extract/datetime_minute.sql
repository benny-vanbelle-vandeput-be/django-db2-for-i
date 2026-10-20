-- golden: extract/datetime_minute
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-20
SELECT MINUTE("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
