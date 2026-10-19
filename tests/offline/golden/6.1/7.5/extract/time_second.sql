-- golden: extract/time_second
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT SECOND("TESTAPP_BOOK"."READING_TIME") AS "X" FROM "TESTAPP_BOOK";
