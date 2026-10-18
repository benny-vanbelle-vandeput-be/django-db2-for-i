-- golden: extract/trunc_datetime_year
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT TRUNC_TIMESTAMP("TESTAPP_BOOK"."PUBLISHED", 'YEAR') AS "X" FROM "TESTAPP_BOOK";
