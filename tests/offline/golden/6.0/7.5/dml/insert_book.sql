-- golden: dml/insert_book
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_book
-- params: [[1, "Db2 for i", {"$datetime": "2026-10-17T13:30:00.123456"}, {"$time": "01:02:03"}, true, 10]]
-- verified: unverified
INSERT INTO "TESTAPP_BOOK" ("AUTHOR_ID", "TITLE", "PUBLISHED", "READING_TIME", "AVAILABLE", "PAGES") VALUES (%s, %s, %s, %s, %s, %s);
