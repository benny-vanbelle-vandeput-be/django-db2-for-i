-- golden: extract/trunc_datetime_month
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT TRUNC_TIMESTAMP("TESTAPP_BOOK"."PUBLISHED", 'MONTH') AS "X" FROM "TESTAPP_BOOK";
