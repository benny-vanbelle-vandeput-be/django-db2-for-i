-- golden: queries/filter_regex_integer
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [["^1[0-9]+$"]]
-- verified: unverified
SELECT "TESTAPP_BOOK"."ID", "TESTAPP_BOOK"."AUTHOR_ID", "TESTAPP_BOOK"."TITLE", "TESTAPP_BOOK"."PUBLISHED", "TESTAPP_BOOK"."READING_TIME", "TESTAPP_BOOK"."AVAILABLE", "TESTAPP_BOOK"."PAGES" FROM "TESTAPP_BOOK" WHERE REGEXP_LIKE("TESTAPP_BOOK"."PAGES", CAST(%s AS NVARCHAR(16370)));
