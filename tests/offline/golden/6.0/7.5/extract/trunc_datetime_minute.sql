-- golden: extract/trunc_datetime_minute
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT TRUNC_TIMESTAMP("TESTAPP_BOOK"."PUBLISHED", 'MI') AS "X" FROM "TESTAPP_BOOK";
