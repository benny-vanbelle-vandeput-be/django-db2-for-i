-- golden: dml/bulk_insert_returning
-- django: 6.1
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["one", "two", "three"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.1.2, 2026-10-30
SELECT "ID" FROM FINAL TABLE (INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s), (%s), (%s)) ORDER BY INPUT SEQUENCE;
