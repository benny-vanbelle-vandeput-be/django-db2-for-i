-- golden: dml/insert_book
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[1, "IBM i"], [1, "Db2 for i", {"$datetime": "2026-10-17T13:30:00.123456"}, {"$time": "01:02:03"}, true, 10]]
-- verified: unverified
INSERT INTO "TESTAPP_AUTHOR" ("ID", "NAME") VALUES (%s, %s);
INSERT INTO "TESTAPP_BOOK" ("AUTHOR_ID", "TITLE", "PUBLISHED", "READING_TIME", "AVAILABLE", "PAGES") VALUES (%s, %s, %s, %s, %s, %s);
