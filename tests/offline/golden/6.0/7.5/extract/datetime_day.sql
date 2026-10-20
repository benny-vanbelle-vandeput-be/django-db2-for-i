-- golden: extract/datetime_day
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT DAY("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
