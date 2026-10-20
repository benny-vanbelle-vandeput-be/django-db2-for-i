-- golden: extract/datetime_iso_year
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: unverified
SELECT INTEGER(VARCHAR_FORMAT("TESTAPP_BOOK"."PUBLISHED", 'IYYY')) AS "X" FROM "TESTAPP_BOOK";
