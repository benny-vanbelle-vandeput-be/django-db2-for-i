-- golden: extract/time_second
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT SECOND("TESTAPP_BOOK"."READING_TIME") AS "X" FROM "TESTAPP_BOOK";
