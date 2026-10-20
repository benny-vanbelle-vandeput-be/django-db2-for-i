-- golden: extract/datetime_second
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT SECOND("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
