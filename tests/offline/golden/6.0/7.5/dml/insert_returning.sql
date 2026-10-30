-- golden: dml/insert_returning
-- django: 6.0
-- profile: 7.5
-- depends: ddl/create_author
-- params: [["returned"]]
-- verified: IBM i 7.5 on PUB400 (TR unknown, Db2 PTF Group unknown), Django 6.0.9, 2026-10-30
SELECT "ID" FROM FINAL TABLE (INSERT INTO "TESTAPP_AUTHOR" ("NAME") VALUES (%s));
