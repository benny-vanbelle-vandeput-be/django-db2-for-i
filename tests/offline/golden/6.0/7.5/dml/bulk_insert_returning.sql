-- golden: dml/bulk_insert_returning
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["one", "two", "three"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-31
SELECT "ID" FROM FINAL TABLE (INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s), (%s), (%s)) ORDER BY INPUT SEQUENCE;
