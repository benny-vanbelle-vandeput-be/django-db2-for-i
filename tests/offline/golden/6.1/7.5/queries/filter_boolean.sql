-- golden: queries/filter_boolean
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-19
SELECT "TESTAPP_BOOK"."ID", "TESTAPP_BOOK"."AUTHOR_ID", "TESTAPP_BOOK"."TITLE", "TESTAPP_BOOK"."PUBLISHED", "TESTAPP_BOOK"."READING_TIME", "TESTAPP_BOOK"."AVAILABLE", "TESTAPP_BOOK"."PAGES" FROM "TESTAPP_BOOK" WHERE "TESTAPP_BOOK"."AVAILABLE";
