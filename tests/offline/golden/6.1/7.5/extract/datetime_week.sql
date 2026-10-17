-- golden: extract/datetime_week
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT WEEK_ISO("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
