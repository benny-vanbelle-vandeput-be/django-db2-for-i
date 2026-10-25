-- golden: dml/insert_book
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author, ddl/create_book
-- params: [[1, "IBM i"], [1, "Db2 for i", {"$datetime": "2026-10-17T13:30:00.123456"}, {"$time": "01:02:03"}, true, 10]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-25
INSERT INTO "TESTAPP_AUTHOR" ("ID", "NAME") VALUES (%s, %s);
INSERT INTO "TESTAPP_BOOK" ("AUTHOR_ID", "TITLE", "PUBLISHED", "READING_TIME", "AVAILABLE", "PAGES") VALUES (%s, %s, %s, %s, %s, %s);
