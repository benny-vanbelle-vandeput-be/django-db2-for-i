-- golden: extract/datetime_day
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-17
SELECT DAY("TESTAPP_BOOK"."PUBLISHED") AS "X" FROM "TESTAPP_BOOK";
