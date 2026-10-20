-- golden: extract/trunc_date_and_time_of_datetime
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT DATE("TESTAPP_BOOK"."PUBLISHED") AS "X", TIME("TESTAPP_BOOK"."PUBLISHED") AS "B" FROM "TESTAPP_BOOK";
