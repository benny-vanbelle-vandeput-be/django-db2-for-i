-- golden: dml/bulk_insert
-- django: 5.2
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["one", "two", "three"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 5.2.18, 2026-10-31
INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s), (%s), (%s);
