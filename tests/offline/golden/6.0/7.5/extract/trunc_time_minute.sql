-- golden: extract/trunc_time_minute
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT TIME(TRUNC_TIMESTAMP(TIMESTAMP(DATE('0001-01-01'), TIME("TESTAPP_BOOK"."READING_TIME")), 'MI')) AS "X" FROM "TESTAPP_BOOK";
