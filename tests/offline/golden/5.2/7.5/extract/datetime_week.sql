-- golden: extract/datetime_week
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT WEEK_ISO("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
