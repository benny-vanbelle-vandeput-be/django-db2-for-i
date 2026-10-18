-- golden: extract/time_second
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT SECOND("TESTAPP_BOOK"."READING_TIME") AS "X" FROM "TESTAPP_BOOK";
