-- golden: extract/datetime_iso_year
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400, 2026-10-18
SELECT INTEGER(VARCHAR_FORMAT("TESTAPP_BOOK"."PUBLISHED", 'IYYY')) AS "X" FROM "TESTAPP_BOOK";
