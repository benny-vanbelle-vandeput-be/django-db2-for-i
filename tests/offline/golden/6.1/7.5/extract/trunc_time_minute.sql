-- golden: extract/trunc_time_minute
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT TIME(TRUNC_TIMESTAMP(TIMESTAMP(DATE('0001-01-01'), TIME("TESTAPP_BOOK"."READING_TIME")), 'MI')) AS "X" FROM "TESTAPP_BOOK";
