-- golden: extract/filter_iso_week_day_sunday
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[7]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-20
SELECT "TESTAPP_BOOK"."ID", "TESTAPP_BOOK"."AUTHOR_ID", "TESTAPP_BOOK"."TITLE", "TESTAPP_BOOK"."PUBLISHED", "TESTAPP_BOOK"."READING_TIME", "TESTAPP_BOOK"."AVAILABLE", "TESTAPP_BOOK"."PAGES" FROM "TESTAPP_BOOK" WHERE DAYOFWEEK_ISO("TESTAPP_BOOK"."PUBLISHED") = %s;
