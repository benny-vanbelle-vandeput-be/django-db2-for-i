-- golden: queries/filter_boolean_column_equals_q
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[100]]
-- verified: unverified
SELECT "TESTAPP_BOOK"."ID", "TESTAPP_BOOK"."AUTHOR_ID", "TESTAPP_BOOK"."TITLE", "TESTAPP_BOOK"."PUBLISHED", "TESTAPP_BOOK"."READING_TIME", "TESTAPP_BOOK"."AVAILABLE", "TESTAPP_BOOK"."PAGES" FROM "TESTAPP_BOOK" WHERE "TESTAPP_BOOK"."AVAILABLE" = (CASE WHEN "TESTAPP_BOOK"."PAGES" < %s THEN TRUE ELSE FALSE END);
