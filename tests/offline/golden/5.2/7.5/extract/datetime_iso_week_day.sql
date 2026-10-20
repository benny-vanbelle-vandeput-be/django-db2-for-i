-- golden: extract/datetime_iso_week_day
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT DAYOFWEEK_ISO("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
