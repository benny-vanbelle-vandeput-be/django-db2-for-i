-- golden: queries/filter_datetime_aware
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[{"$datetime": "2026-10-17T13:30:00.123456"}]]
-- verified: unverified
SELECT "TESTAPP_BOOK"."ID", "TESTAPP_BOOK"."AUTHOR_ID", "TESTAPP_BOOK"."TITLE", "TESTAPP_BOOK"."PUBLISHED", "TESTAPP_BOOK"."READING_TIME", "TESTAPP_BOOK"."AVAILABLE", "TESTAPP_BOOK"."PAGES" FROM "TESTAPP_BOOK" WHERE "TESTAPP_BOOK"."PUBLISHED" >= %s;
